

from qgis.core import QgsSpatialIndex, QgsWkbTypes, QgsGeometry
import re
import math

# ─── Couches à analyser (liste blanche) ───────────────────────────────────────
ALLOWED_LAYERS = [
    'NRO', 'SRO', 'PA', 'PB', 'SUPPORT', 'ADRESSE',
    'CB_DI', 'CM_DI', 'PEP_DI', 'ZNRO', 'ZSRO', 'ZPA', 'ZPBO'
]

# Supports orphelins tolérés (équipements terminaux valides)
ORPHAN_EXEMPT_SUPPORTS = [
    'NRA', 'SHELTER', 'NOEUD VIRTUEL', 'SRO', 'NRO', 'ARMOIRE DE RUE'
]

LAYER_ID_FIELDS = {
    'PA':      'pcn_code',
    'PB':      'pcn_code',
    'ZPA':     'pcn_code',
    'ZPBO':    'pcn_code',
    'ADRESSE': 'ad_code',
    'SUPPORT': 'pt_codeext',
    'CB_DI':   'cl_codeext',
    'CM_DI':   'cm_codeext',
    'PEP_DI':  'pcn_code',
    'ZSRO':    'zs_code',
    'ZNRO':    'zn_code',
    'NRO':     'nd_code',
    'SRO':     'nd_code',
}

SNAP_TOLERANCE = 0.5
LINE_TOLERANCE = 1.0

# Valeurs autorisées cb_capafo par type
CB_CAPAFO_ALLOWED = {
    'D3': [1],
    'DI': [12, 24, 36, 48, 72, 144],
    'TR': [36, 72, 144, 288, 432, 576, 720],
}

# Règle pcn_cb_ent selon pcn_ftth
def calc_cb_ent(ftth):
    if ftth <= 0: return None
    if ftth <= 5: return 6
    if ftth <= 10: return 12
    if ftth <= 20: return 24
    if ftth <= 30: return 36
    if ftth <= 60: return 72
    return None

# Règle zp_capamax selon pcn_ftth
def calc_capamax(ftth):
    if ftth <= 0: return None
    if ftth <= 5: return 6
    if ftth <= 10: return 12
    if ftth <= 20: return 24
    if ftth <= 30: return 36
    if ftth <= 60: return 72
    return None


# ─── Utilitaires ──────────────────────────────────────────────────────────────

def is_allowed_layer(layer):
    """Vérifie si la couche est dans la liste blanche."""
    name = layer.name().upper().strip()
    for allowed in ALLOWED_LAYERS:
        if allowed == name or name.endswith('_' + allowed) or \
                name.startswith(allowed + '_') or allowed in name:
            # Exclure mob_infra, mob_support et autres couches non livrables
            if any(x in name for x in ['MOB_', 'CONDUITE_ORANGE',
                                         'CONDUITE_CTM', 'CONDUITE_PRIVE',
                                         'AERIEN_ORANGE', 'AERIEN_ENEDIS',
                                         'CREATION_']):
                return False
            return True
    return False


def get_id_field(layer):
    if layer is None:
        return None
    name = layer.name().upper().strip()
    for key, field in LAYER_ID_FIELDS.items():
        if key in name:
            return field
    fields = layer.fields()
    return fields[0].name() if fields.count() > 0 else None


def get_display_id(feature, id_field):
    if id_field:
        try:
            val = feature[id_field]
            if val is not None and str(val).strip() not in ('', 'NULL'):
                return str(val).strip()
        except Exception:
            pass
    return f"fid={feature.id()}"


def build_spatial_index(layer):
    index = QgsSpatialIndex()
    if layer:
        for f in layer.getFeatures():
            if f.geometry() and not f.geometry().isNull():
                index.addFeature(f)
    return index


def has_field(layer, field_name):
    return field_name in [f.name() for f in layer.fields()]


def field_val(feature, field_name):
    try:
        val = feature[field_name]
        return str(val).strip() if val is not None else ''
    except Exception:
        return ''


def field_int(feature, field_name):
    try:
        val = feature[field_name]
        if val is None or str(val).strip() in ('', 'NULL', 'None'):
            return None
        return int(float(str(val)))
    except (ValueError, TypeError):
        return None


def line_passes_through_point(line_layer, point_geom, index, tolerance):
    bbox = point_geom.boundingBox()
    bbox.grow(tolerance)
    for cid in index.intersects(bbox):
        f = line_layer.getFeature(cid)
        fgeom = f.geometry()
        if fgeom and not fgeom.isNull():
            if point_geom.distance(fgeom) <= tolerance:
                return True
    return False


def point_has_neighbor(point_geom, layer, index, tolerance):
    bbox = point_geom.boundingBox()
    bbox.grow(tolerance)
    for cid in index.intersects(bbox):
        f = layer.getFeature(cid)
        fgeom = f.geometry()
        if fgeom and not fgeom.isNull():
            if point_geom.distance(fgeom) <= tolerance:
                return True
    return False


def err(fid, did, code, layer_name, type_err, detail):
    return {
        'fid': fid,
        'display_id': did,
        'leo_code': code,
        'layer_name': layer_name,
        'type': type_err,
        'detail': detail
    }


# ─── Géométrie universelle ────────────────────────────────────────────────────

def is_cbdi_intrasite(feature, layer, support_layer=None):
    """
    Retourne True si le câble CB_DI est un vrai intrasite sur support :
      - cb_long == 0
      - ET au moins un nœud (ou le point de la géométrie) se trouve
        à moins de SNAP_TOLERANCE d'un support.
    Si support_layer est None ou absent, la condition de proximité
    ne peut pas être vérifiée → on retourne False (erreur remontée).
    """
    if 'CB_DI' not in layer.name().upper():
        return False
    if not has_field(layer, 'cb_long'):
        return False
    try:
        val = feature['cb_long']
        if val is None or str(val).strip() in ('', 'NULL', 'None'):
            return False
        if float(str(val)) != 0.0:
            return False
    except (ValueError, TypeError):
        return False

    # cb_long == 0 confirmé : vérifier la présence sur un support
    if support_layer is None:
        return False

    geom = feature.geometry()
    # Construire un point de référence : premier vertex disponible,
    # ou centroïde si la géométrie est dégénérée/nulle
    ref_point = None
    if geom and not geom.isNull() and not geom.isEmpty():
        vertices = list(geom.vertices())
        if vertices:
            ref_point = QgsGeometry.fromPointXY(
                __import__('qgis.core', fromlist=['QgsPointXY']).QgsPointXY(
                    vertices[0].x(), vertices[0].y()))

    if ref_point is None:
        # Géométrie absente : on ne peut pas tester la proximité
        return False

    sup_index = build_spatial_index(support_layer)
    bbox = ref_point.boundingBox()
    bbox.grow(SNAP_TOLERANCE)
    for cid in sup_index.intersects(bbox):
        sg = support_layer.getFeature(cid).geometry()
        if sg and not sg.isNull():
            if ref_point.distance(sg) <= SNAP_TOLERANCE:
                return True
    return False


def check_invalid_geometries(layer, support_layer=None):
    errors = []
    id_field = get_id_field(layer)
    lname = layer.name()
    for feature in layer.getFeatures():
        geom = feature.geometry()
        did = get_display_id(feature, id_field)
        fid = feature.id()
        if geom is None or geom.isNull():
            # CB_DI intrasite sur support (cb_long=0) : toléré
            if is_cbdi_intrasite(feature, layer, support_layer):
                continue
            errors.append(err(fid, did, 'GEOM001', lname,
                              'Géométrie nulle', f'{did} : sans géométrie'))
        elif geom.isEmpty():
            # CB_DI intrasite sur support (cb_long=0) : toléré
            if is_cbdi_intrasite(feature, layer, support_layer):
                continue
            errors.append(err(fid, did, 'GEOM002', lname,
                              'Géométrie vide', f'{did} : géométrie vide'))
        elif not geom.isGeosValid():
            # CB_DI intrasite sur support (cb_long=0) : toléré
            if is_cbdi_intrasite(feature, layer, support_layer):
                continue
            errors.append(err(fid, did, 'GEOM003', lname,
                              'Géométrie invalide',
                              f'{did} : {geom.lastError()}'))
    return errors


def check_multipart(layer):
    errors = []
    if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.LineGeometry:
        return errors
    id_field = get_id_field(layer)
    lname = layer.name()
    for feature in layer.getFeatures():
        geom = feature.geometry()
        if geom is None or geom.isNull():
            continue
        if geom.isMultipart() and len(geom.asGeometryCollection()) > 1:
            did = get_display_id(feature, id_field)
            errors.append(err(feature.id(), did, 'GEOM004', lname,
                              'Multi-partie',
                              f'{did} : {len(geom.asGeometryCollection())} parties'))
    return errors


def check_duplicates(layer, tolerance=0.01):
    errors = []
    id_field = get_id_field(layer)
    lname = layer.name()
    features = list(layer.getFeatures())
    field_names = [f.name() for f in layer.fields()]
    index = build_spatial_index(layer)
    checked = set()
    for f in features:
        geom = f.geometry()
        fid = f.id()
        if geom is None or geom.isNull() or fid in checked:
            continue
        bbox = geom.boundingBox()
        bbox.grow(tolerance)
        for cid in index.intersects(bbox):
            if cid == fid or cid in checked:
                continue
            other = layer.getFeature(cid)
            og = other.geometry()
            if og is None or og.isNull() or not geom.equals(og):
                continue
            if id_field and id_field in field_names:
                if str(f[id_field]).strip() != str(other[id_field]).strip():
                    continue
            if not all(str(f[fl]).strip() == str(other[fl]).strip()
                       for fl in field_names):
                continue
            did1 = get_display_id(f, id_field)
            errors.append(err(fid, did1, 'GEOM005', lname,
                              'Doublon exact',
                              f'{did1} et fid={cid} : même géométrie et attributs'))
            checked.add(cid)
    return errors


def check_crossings(layer):
    errors = []
    if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.LineGeometry:
        return errors
    id_field = get_id_field(layer)
    lname = layer.name()
    features = list(layer.getFeatures())
    index = build_spatial_index(layer)
    checked = set()
    for f in features:
        geom = f.geometry()
        fid = f.id()
        if geom is None or geom.isNull():
            continue
        for cid in index.intersects(geom.boundingBox()):
            if cid == fid:
                continue
            pair = tuple(sorted([fid, cid]))
            if pair in checked:
                continue
            checked.add(pair)
            og = layer.getFeature(cid).geometry()
            if og and not og.isNull() and geom.crosses(og):
                did = get_display_id(f, id_field)
                did2 = get_display_id(layer.getFeature(cid), id_field)
                errors.append(err(fid, did, 'GEOM006', lname,
                                  'Croisement sans nœud',
                                  f'{did} et {did2} : croisement sans jonction'))
    return errors


def check_missing_id(layer):
    errors = []
    id_field = get_id_field(layer)
    if not id_field or not has_field(layer, id_field):
        return errors
    lname = layer.name()
    for feature in layer.getFeatures():
        val = feature[id_field]
        if val is None or str(val).strip() in ('', 'NULL'):
            did = f"fid={feature.id()}"
            errors.append(err(feature.id(), did, 'GEOM007', lname,
                              'Code manquant',
                              f'{did} : champ "{id_field}" NULL ou vide'))
    return errors


def check_containment(layer, container_layer):
    errors = []
    if container_layer is None:
        return errors
    id_field = get_id_field(layer)
    lname = layer.name()
    index = build_spatial_index(container_layer)
    for feature in layer.getFeatures():
        geom = feature.geometry()
        if geom is None or geom.isNull():
            continue
        did = get_display_id(feature, id_field)
        candidates = index.intersects(geom.boundingBox())
        contained = any(
            container_layer.getFeature(cid).geometry() and
            container_layer.getFeature(cid).geometry().contains(geom)
            for cid in candidates
        )
        if not contained:
            errors.append(err(feature.id(), did, 'ZPA-ZSRO', lname,
                              'Hors ZSRO',
                              f'{did} : non contenu dans une ZSRO'))
    return errors


# ─── ADRESSE ──────────────────────────────────────────────────────────────────

def check_adresse(layer):
    """AD001a, AD013, AD015, AD-IMB, AD-FTTH"""
    errors = []
    lname = layer.name()
    seen_combos = {}
    combo_fields = ['ad_numero', 'ad_rep', 'ad_nombat', 'ad_nomvoie', 'ad_insee']
    combo_ok = all(has_field(layer, f) for f in combo_fields)

    for feature in layer.getFeatures():
        fid = feature.id()
        ad_code = field_val(feature, 'ad_code')
        did = ad_code if ad_code else f"fid={fid}"

        # AD001a : format ad_code → AD976XXXXXXXX
        if ad_code and not re.match(r'^AD976\d+$', ad_code):
            errors.append(err(fid, did, 'AD001a', lname,
                              'AD001a - Format ad_code invalide',
                              f'{did} : ad_code "{ad_code}" attendu AD976XXXXX'))

        # AD013 : ad_postal NULL ou vide
        if has_field(layer, 'ad_postal'):
            if not field_val(feature, 'ad_postal'):
                errors.append(err(fid, did, 'AD013', lname,
                                  'AD013 - ad_postal manquant',
                                  f'{did} : ad_postal NULL ou vide'))

        # AD015 : doublons combinés
        if combo_ok:
            combo = tuple(field_val(feature, f) for f in combo_fields)
            if combo in seen_combos:
                errors.append(err(fid, did, 'AD015', lname,
                                  'AD015 - Doublon adresse',
                                  f'{did} : doublon avec {seen_combos[combo]}'))
            else:
                seen_combos[combo] = did

        # AD-IMB : pcn_imb = OUI si pcn_ftth >= 4
        if has_field(layer, 'pcn_ftth') and has_field(layer, 'pcn_imb'):
            ftth = field_int(feature, 'pcn_ftth')
            imb = field_val(feature, 'pcn_imb').upper()
            if ftth is not None:
                expected = 'OUI' if ftth >= 4 else 'NON'
                if imb and imb != expected:
                    errors.append(err(fid, did, 'AD-IMB', lname,
                                      'AD-IMB - pcn_imb incohérent',
                                      f'{did} : pcn_ftth={ftth} → '
                                      f'pcn_imb devrait être {expected}, '
                                      f'valeur: {imb}'))

        # AD-FTTH : pcn_ftth = pcn_log + pcn_pro
        if all(has_field(layer, f) for f in ['pcn_ftth', 'pcn_log', 'pcn_pro']):
            ftth = field_int(feature, 'pcn_ftth')
            log = field_int(feature, 'pcn_log') or 0
            pro = field_int(feature, 'pcn_pro') or 0
            if ftth is not None and ftth != log + pro:
                errors.append(err(fid, did, 'AD-FTTH', lname,
                                  'AD-FTTH - pcn_ftth incohérent',
                                  f'{did} : pcn_ftth={ftth} ≠ '
                                  f'pcn_log({log})+pcn_pro({pro})='
                                  f'{log+pro}'))
    return errors


# ─── CB_DI ────────────────────────────────────────────────────────────────────

def check_cbdi(layer, cm_layer, support_layer):
    """CBDI009, CBDI010, CBDI011, CBDI012, CB-FORMAT, CB-CAPAFO, CB-LONG"""
    errors = []
    lname = layer.name()
    id_field = get_id_field(layer)
    cm_index = build_spatial_index(cm_layer) if cm_layer else None
    sup_index = build_spatial_index(support_layer) if support_layer else None

    # Construire dict pt_codeext → feature pour CBDI011/012
    sup_dict = {}
    if support_layer and has_field(support_layer, 'pt_codeext'):
        for sf in support_layer.getFeatures():
            code = field_val(sf, 'pt_codeext')
            if code:
                sup_dict[code] = sf.geometry()

    for feature in layer.getFeatures():
        geom = feature.geometry()
        if geom is None or geom.isNull():
            continue
        fid = feature.id()
        did = get_display_id(feature, id_field)

        # CB-FORMAT : cl_codeext doit commencer par D1_, D2_, D3_, TR_
        if has_field(layer, 'cl_codeext') and has_field(layer, 'cb_typelog'):
            code = field_val(feature, 'cl_codeext')
            typelog = field_val(feature, 'cb_typelog').upper()
            if code and typelog == 'DI':
                if not re.match(r'^(D1_|D2_|D3_)', code):
                    errors.append(err(fid, did, 'CB-FORMAT', lname,
                                      'CB-FORMAT - cl_codeext invalide',
                                      f'{did} : code "{code}" devrait '
                                      f'commencer par D1_, D2_ ou D3_'))
            elif code and typelog == 'TR':
                if not code.startswith('TR_'):
                    errors.append(err(fid, did, 'CB-FORMAT', lname,
                                      'CB-FORMAT - cl_codeext invalide',
                                      f'{did} : code "{code}" devrait '
                                      f'commencer par TR_'))

        # CB-CAPAFO : valeurs autorisées selon cb_typelog
        if has_field(layer, 'cb_capafo') and has_field(layer, 'cb_typelog'):
            typelog = field_val(feature, 'cb_typelog').upper()
            capafo = field_int(feature, 'cb_capafo')
            if capafo is not None and typelog in CB_CAPAFO_ALLOWED:
                if capafo not in CB_CAPAFO_ALLOWED[typelog]:
                    errors.append(err(fid, did, 'CB-CAPAFO', lname,
                                      'CB-CAPAFO - Capacité invalide',
                                      f'{did} : cb_capafo={capafo} non '
                                      f'autorisé pour {typelog} '
                                      f'(autorisé: '
                                      f'{CB_CAPAFO_ALLOWED[typelog]})'))

        # CB-LONG : longueur > 0 et ≤ 2100m
        # longueur = 0 : intrasite si posé sur support (valide), sinon géométrie invalide
        if has_field(layer, 'cb_long'):
            try:
                lng = float(field_val(feature, 'cb_long') or 0)
                if lng == 0:
                    # Vérifier si le câble est sur un support
                    on_support = False
                    if sup_index and support_layer:
                        bbox = geom.boundingBox()
                        bbox.grow(SNAP_TOLERANCE)
                        for cid in sup_index.intersects(bbox):
                            sg = support_layer.getFeature(cid).geometry()
                            if sg and not sg.isNull():
                                if geom.distance(sg) <= SNAP_TOLERANCE:
                                    on_support = True
                                    break
                    if not on_support:
                        errors.append(err(fid, did, 'CB-LONG-ZERO', lname,
                                          'CB-LONG-ZERO - Câble longueur 0 hors support',
                                          f'{did} : cb_long=0 sans être posé '
                                          f'sur un support — géométrie non valide '
                                          f'(longueur 0 acceptée uniquement en intrasite sur support)'))
                elif lng > 2100:
                    errors.append(err(fid, did, 'CB-LONG', lname,
                                      'CB-LONG - Câble trop long',
                                      f'{did} : cb_long={lng:.1f}m '
                                      f'dépasse 2100m'))
            except (ValueError, TypeError):
                pass

        line = (geom.asPolyline() if not geom.isMultipart()
                else geom.asMultiPolyline()[0]
                if geom.isMultipart() and geom.asMultiPolyline() else [])
        if len(line) < 2:
            continue

        start_pt = QgsGeometry.fromPointXY(line[0])
        end_pt = QgsGeometry.fromPointXY(line[-1])

        # CBDI009/010 : extrémités à plus de 0.01m d'une extrémité CM
        if cm_layer and cm_index:
            if not line_passes_through_point(
                    cm_layer, start_pt, cm_index, 0.5):
                errors.append(err(fid, did, 'CBDI009', lname,
                                  'CBDI009 - StartPoint hors CM',
                                  f'{did} : début du câble non accroché '
                                  f'à un cheminement CM_DI'))
            if not line_passes_through_point(
                    cm_layer, end_pt, cm_index, 0.5):
                errors.append(err(fid, did, 'CBDI010', lname,
                                  'CBDI010 - EndPoint hors CM',
                                  f'{did} : fin du câble non accrochée '
                                  f'à un cheminement CM_DI'))

        # CBDI011 : cl_nd1 ≠ StartPoint
        if has_field(layer, 'cl_nd1'):
            nd1 = field_val(feature, 'cl_nd1')
            if nd1 and nd1 in sup_dict:
                nd1_geom = sup_dict[nd1]
                if nd1_geom and start_pt.distance(nd1_geom) > SNAP_TOLERANCE:
                    errors.append(err(fid, did, 'CBDI011', lname,
                                      'CBDI011 - cl_nd1 ≠ StartPoint',
                                      f'{did} : cl_nd1="{nd1}" écart='
                                      f'{start_pt.distance(nd1_geom):.2f}m '
                                      f'avec le début du câble'))

        # CBDI012 : cl_nd2 ≠ EndPoint
        if has_field(layer, 'cl_nd2'):
            nd2 = field_val(feature, 'cl_nd2')
            if nd2 and nd2 in sup_dict:
                nd2_geom = sup_dict[nd2]
                if nd2_geom and end_pt.distance(nd2_geom) > SNAP_TOLERANCE:
                    errors.append(err(fid, did, 'CBDI012', lname,
                                      'CBDI012 - cl_nd2 ≠ EndPoint',
                                      f'{did} : cl_nd2="{nd2}" écart='
                                      f'{end_pt.distance(nd2_geom):.2f}m '
                                      f'avec la fin du câble'))
    return errors


# ─── CM_DI ────────────────────────────────────────────────────────────────────

def check_cmdi(layer):
    """CMDI005, CMDI009, CM-AVCT"""
    errors = []
    lname = layer.name()
    id_field = get_id_field(layer)
    AVCT_VALID = {'E', 'C', 'S'}
    PCN_SUP_VALID = {
        'D3', 'AERIEN_ORANGE', 'AERIEN_ENEDIS', 'CONDUITE_ORANGE',
        'CONDUITE_CTM', 'CREATION_CONDUITE_TR', 'CREATION_CONDUITE_DI',
        'CREATION_AERIEN', 'CONDUITE_PRIVE', 'FACADE', 'IMMEUBLE',
        'CREATION_CONDUITE_CO', 'CONDUITE_MNU', 'RA'
    }

    for feature in layer.getFeatures():
        fid = feature.id()
        did = get_display_id(feature, id_field)

        # CM-AVCT : valeurs autorisées E, C, S
        if has_field(layer, 'cm_avct'):
            avct = field_val(feature, 'cm_avct').upper()
            if avct and avct not in AVCT_VALID:
                errors.append(err(fid, did, 'CM-AVCT', lname,
                                  'CM-AVCT - cm_avct invalide',
                                  f'{did} : cm_avct="{avct}" '
                                  f'(autorisé: E, C, S)'))

        # CMDI005 : cm_avct=C mais pcn_sup inconnu
        if has_field(layer, 'cm_avct') and has_field(layer, 'pcn_sup'):
            avct = field_val(feature, 'cm_avct').upper()
            pcn_sup = field_val(feature, 'pcn_sup').upper()
            if avct == 'C' and pcn_sup and pcn_sup not in PCN_SUP_VALID:
                errors.append(err(fid, did, 'CMDI005', lname,
                                  'CMDI005 - pcn_sup invalide',
                                  f'{did} : cm_avct=C mais pcn_sup='
                                  f'"{pcn_sup}" non reconnu'))

        # CMDI009 : cm_avct=C et cm_compo NULL sur conduite
        if has_field(layer, 'cm_avct') and has_field(layer, 'cm_compo') \
                and has_field(layer, 'pcn_sup'):
            avct = field_val(feature, 'cm_avct').upper()
            compo = field_val(feature, 'cm_compo')
            pcn_sup = field_val(feature, 'pcn_sup').upper()
            if avct == 'C' and 'CONDUITE' in pcn_sup and not compo:
                errors.append(err(fid, did, 'CMDI009', lname,
                                  'CMDI009 - cm_compo manquant',
                                  f'{did} : conduite créée sans '
                                  f'cm_compo (fourreaux)'))
    return errors


# ─── NRO ──────────────────────────────────────────────────────────────────────

def check_nro(layer, support_layer):
    """NRO002 : NRO à plus de 0.1m d'un support"""
    errors = []
    lname = layer.name()
    id_field = get_id_field(layer)
    if support_layer is None:
        return errors
    sup_index = build_spatial_index(support_layer)

    for feature in layer.getFeatures():
        geom = feature.geometry()
        if geom is None or geom.isNull():
            continue
        fid = feature.id()
        did = get_display_id(feature, id_field)
        bbox = geom.boundingBox()
        bbox.grow(1.0)
        candidates = sup_index.intersects(bbox)
        min_dist = min(
            (geom.distance(support_layer.getFeature(cid).geometry())
             for cid in candidates
             if support_layer.getFeature(cid).geometry()),
            default=float('inf')
        )
        if min_dist > 0.1:
            errors.append(err(fid, did, 'NRO002', lname,
                              'NRO002 - NRO sans support proche',
                              f'{did} : NRO à {min_dist:.2f}m '
                              f'du support le plus proche (max 0.1m)'))
    return errors


# ─── ZNRO ─────────────────────────────────────────────────────────────────────

def check_znro(layer):
    """ZNRO002 : zn_nroref format CODE_INSEE/NRO/TRIGRAMME"""
    errors = []
    lname = layer.name()
    id_field = get_id_field(layer)
    if not has_field(layer, 'zn_nroref'):
        return errors

    for feature in layer.getFeatures():
        fid = feature.id()
        did = get_display_id(feature, id_field)
        val = field_val(feature, 'zn_nroref')
        # Format attendu : 97XXX/NRO/TRIGRAMME
        if val and not re.match(r'^\d{5}/NRO/[A-Z]{2,5}$', val):
            errors.append(err(fid, did, 'ZNRO002', lname,
                              'ZNRO002 - zn_nroref non conforme',
                              f'{did} : zn_nroref="{val}" — '
                              f'attendu: 97XXX/NRO/TRIGRAMME '
                              f'(ex: 97307/NRO/PZI)'))
    return errors


# ─── PB ───────────────────────────────────────────────────────────────────────

def check_pb(layer, support_layer, cb_layer, cm_layer):
    """PB001, PB-SUP, PB12-FORBID, PB-CB, PB-UMFTTH, PB-CBENT, PB016, PB017"""
    errors = []
    lname = layer.name()
    id_field = get_id_field(layer)

    sup_index = build_spatial_index(support_layer) if support_layer else None
    cb_index  = build_spatial_index(cb_layer) if cb_layer else None
    cm_index  = build_spatial_index(cm_layer) if cm_layer else None
    PB12_FORBIDDEN = [
        'POTEAU ORANGE', 'POTEAU ENEDIS',
        'ANCRAGE FACADE', 'ARMOIRE DE RUE', 'SHELTER'
    ]

    for feature in layer.getFeatures():
        geom = feature.geometry()
        if geom is None or geom.isNull():
            continue
        fid = feature.id()
        did = get_display_id(feature, id_field)
        pb_type = field_val(feature, 'pcn_pbtyp').upper() \
            if has_field(layer, 'pcn_pbtyp') else ''

        # PB001 : CM_DI obligatoire
        if cm_layer and cm_index:
            if not line_passes_through_point(
                    cm_layer, geom, cm_index, LINE_TOLERANCE):
                errors.append(err(fid, did, 'PB001', lname,
                                  'PB001 - PB sans CM_DI',
                                  f'{did} : aucun CM_DI ne passe par ce PB'))

        # PB sans support
        if support_layer and sup_index:
            has_sup = point_has_neighbor(
                geom, support_layer, sup_index, SNAP_TOLERANCE)
            if not has_sup:
                errors.append(err(fid, did, 'PB-SUP', lname,
                                  'PB sans support',
                                  f'{did} : aucun support aux mêmes coordonnées'))
            elif 'PB12' in pb_type and support_layer and \
                    has_field(support_layer, 'pcn_newsup'):
                # PB12 sur support interdit
                bbox = geom.boundingBox()
                bbox.grow(SNAP_TOLERANCE)
                nearest = min(
                    ((support_layer.getFeature(cid),
                      geom.distance(support_layer.getFeature(cid).geometry()))
                     for cid in sup_index.intersects(bbox)
                     if support_layer.getFeature(cid).geometry()),
                    key=lambda x: x[1], default=(None, float('inf'))
                )
                if nearest[0] is not None and nearest[1] <= SNAP_TOLERANCE:
                    pcn = field_val(nearest[0], 'pcn_newsup').upper()
                    for forbidden in PB12_FORBIDDEN:
                        if forbidden in pcn:
                            errors.append(err(fid, did, 'PB12-FORBID', lname,
                                              'PB12 sur support interdit',
                                              f'{did} : PB12 sur '
                                              f'"{field_val(nearest[0], "pcn_newsup")}" '
                                              f'— CHAMBRE ORANGE obligatoire'))
                            break

        # PB sans CB_DI
        if cb_layer and cb_index:
            if not line_passes_through_point(
                    cb_layer, geom, cb_index, LINE_TOLERANCE):
                errors.append(err(fid, did, 'PB-CB', lname,
                                  'PB sans CB_DI',
                                  f'{did} : aucun câble CB_DI '
                                  f'ne passe par ce PB'))

        # PB-UMFTTH : pcn_umftth selon type
        if has_field(layer, 'pcn_umftth') and has_field(layer, 'pcn_pbtyp') \
                and has_field(layer, 'pcn_ftth'):
            umftth = field_int(feature, 'pcn_umftth')
            ftth = field_int(feature, 'pcn_ftth')
            if umftth is not None and pb_type:
                expected = None
                if 'PBR6E' in pb_type:
                    expected = 0
                elif any(x in pb_type for x in
                         ['PBR6M', 'PBR12E', 'PBR12M']):
                    expected = 1
                elif 'PB6' in pb_type:
                    # PB6 avec pcn_ftth=6 → pcn_umftth=2, sinon 1
                    expected = 2 if (ftth is not None and ftth == 6) else 1
                elif 'PB12' in pb_type:
                    expected = 2
                elif 'PBI' in pb_type and ftth:
                    expected = math.ceil(ftth / 5)
                if expected is not None and umftth != expected:
                    errors.append(err(fid, did, 'PB-UMFTTH', lname,
                                      'PB-UMFTTH - pcn_umftth invalide',
                                      f'{did} : {pb_type} devrait avoir '
                                      f'pcn_umftth={expected}, '
                                      f'valeur: {umftth}'))

        # PB016/017 : pcn_cb_ent selon pcn_ftth
        if has_field(layer, 'pcn_cb_ent') and has_field(layer, 'pcn_ftth'):
            ftth = field_int(feature, 'pcn_ftth')
            cb_ent = field_int(feature, 'pcn_cb_ent')
            if ftth is not None and cb_ent is not None:
                expected_cb = calc_cb_ent(ftth)
                if expected_cb and cb_ent != expected_cb:
                    code = 'PB016' if 'PB6' in pb_type else \
                           'PB017' if 'PB12' in pb_type else 'PB-CBENT'
                    errors.append(err(fid, did, code, lname,
                                      f'{code} - pcn_cb_ent invalide',
                                      f'{did} : pcn_ftth={ftth} → '
                                      f'pcn_cb_ent devrait être '
                                      f'{expected_cb}FO, valeur: {cb_ent}'))
    return errors


# ─── SUPPORT ──────────────────────────────────────────────────────────────────

def check_support(layer, pb_layer, pa_layer, cb_layer, cm_layer):
    """SUPP001 + Support orphelin (avec exemptions NRA/SHELTER/NOEUD VIRTUEL)"""
    errors = []
    lname = layer.name()
    id_field = get_id_field(layer)

    pb_index = build_spatial_index(pb_layer)
    pa_index = build_spatial_index(pa_layer)
    cb_index = build_spatial_index(cb_layer)
    cm_index = build_spatial_index(cm_layer)
    PT_TYPEPHY_VALID = {'A', 'C', 'F', 'I', 'Z'}

    for feature in layer.getFeatures():
        geom = feature.geometry()
        if geom is None or geom.isNull():
            continue
        fid = feature.id()
        did = get_display_id(feature, id_field)

        # pt_typephy valeurs autorisées
        if has_field(layer, 'pt_typephy'):
            typephy = field_val(feature, 'pt_typephy').upper()
            if typephy and typephy not in PT_TYPEPHY_VALID:
                errors.append(err(fid, did, 'SUPP-TYPE', lname,
                                  'SUPP-TYPE - pt_typephy invalide',
                                  f'{did} : pt_typephy="{typephy}" '
                                  f'(autorisé: A, C, F, I, Z)'))

        # Vérifier si ce support est exempté des règles orphelin
        pcn_newsup = field_val(feature, 'pcn_newsup').upper() \
            if has_field(layer, 'pcn_newsup') else ''
        is_exempt = any(ex in pcn_newsup for ex in ORPHAN_EXEMPT_SUPPORTS)
        if is_exempt:
            continue

        has_pb = pb_layer and point_has_neighbor(
            geom, pb_layer, pb_index, SNAP_TOLERANCE)
        has_pa = pa_layer and point_has_neighbor(
            geom, pa_layer, pa_index, SNAP_TOLERANCE)
        has_cb = cb_layer and line_passes_through_point(
            cb_layer, geom, cb_index, LINE_TOLERANCE)
        has_cm = cm_layer and line_passes_through_point(
            cm_layer, geom, cm_index, LINE_TOLERANCE)

        if not has_pb and not has_pa and not has_cb and not has_cm:
            errors.append(err(fid, did, 'SUPP001', lname,
                              'SUPP001 - Support orphelin',
                              f'{did} : aucun PB/PA accroché ni '
                              f'CB_DI/CM_DI passant dessus'))
    return errors


# ─── ZPA ──────────────────────────────────────────────────────────────────────

def check_zpa(layer, zsro_layer, pb_layer, adresse_layer):
    """
    ZPA005, ZPA008, ZPA-UMTOT, ZPA-UMUTI +
    ZPA-DEBORD : ZPA dépasse la ZSRO
    ZPA-TROU   : Zone non couverte dans la ZSRO
    ZPA-ADJ    : ZPA non adjacentes entre elles
    """
    errors = []
    lname = layer.name()
    id_field = get_id_field(layer)

    # ── ZPA entièrement dans ZSRO + détection dépassement ─────────────
    if zsro_layer:
        zsro_feats = list(zsro_layer.getFeatures())
        if zsro_feats:
            zsro_geom = zsro_feats[0].geometry()
            # Union de toutes les ZSRO si plusieurs
            for zf in zsro_feats[1:]:
                zsro_geom = zsro_geom.combine(zf.geometry())

            for feature in layer.getFeatures():
                geom = feature.geometry()
                if geom is None or geom.isNull():
                    continue
                fid = feature.id()
                did = get_display_id(feature, id_field)

                if not zsro_geom.contains(geom):
                    # Calculer la partie qui dépasse
                    debord = geom.difference(zsro_geom)
                    if debord and not debord.isEmpty():
                        errors.append(err(
                            fid, did, 'ZPA-DEBORD', lname,
                            'ZPA-DEBORD - ZPA dépasse ZSRO',
                            f'{did} : une partie de la ZPA se trouve '
                            f'en dehors de la ZSRO — affichée en jaune'
                        ))

            # ── ZPA-TROU : zone ZSRO non couverte par ZPA ─────────────
            all_zpa_features = list(layer.getFeatures())
            if all_zpa_features:
                # Union de toutes les ZPA
                union_zpa = all_zpa_features[0].geometry()
                for zpa_f in all_zpa_features[1:]:
                    g = zpa_f.geometry()
                    if g and not g.isNull():
                        union_zpa = union_zpa.combine(g)

                # Zone non couverte = ZSRO - union(ZPA)
                trou = zsro_geom.difference(union_zpa)
                if trou and not trou.isEmpty():
                    area = trou.area()
                    if area > 1.0:  # seuil 1m² pour éviter artefacts
                        errors.append(err(
                            -1, 'ZSRO', 'ZPA-TROU', lname,
                            'ZPA-TROU - Zone ZSRO non couverte',
                            f'Une zone de {area:.1f}m² à l\'intérieur '
                            f'de la ZSRO n\'est couverte par aucune ZPA '
                            f'— affichée en jaune'
                        ))

    # ── ZPA-UMTOT = pcn_umuti + pcn_umrsv ────────────────────────────
    for feature in layer.getFeatures():
        fid = feature.id()
        did = get_display_id(feature, id_field)
        if all(has_field(layer, f) for f in
               ['pcn_umtot', 'pcn_umuti', 'pcn_umrsv']):
            umtot = field_int(feature, 'pcn_umtot')
            umuti = field_int(feature, 'pcn_umuti') or 0
            umrsv = field_int(feature, 'pcn_umrsv') or 0
            if umtot is not None and umtot != umuti + umrsv:
                errors.append(err(fid, did, 'ZPA-UMTOT', lname,
                                  'ZPA-UMTOT - pcn_umtot incohérent',
                                  f'{did} : pcn_umtot={umtot} ≠ '
                                  f'umuti({umuti})+umrsv({umrsv})='
                                  f'{umuti + umrsv}'))

        # ZPA-UMUTI = pcn_umftth + pcn_umftte
        if all(has_field(layer, f) for f in
               ['pcn_umuti', 'pcn_umftth', 'pcn_umftte']):
            umuti = field_int(feature, 'pcn_umuti')
            umftth = field_int(feature, 'pcn_umftth') or 0
            umftte = field_int(feature, 'pcn_umftte') or 0
            if umuti is not None and umuti != umftth + umftte:
                errors.append(err(fid, did, 'ZPA-UMUTI', lname,
                                  'ZPA-UMUTI - pcn_umuti incohérent',
                                  f'{did} : pcn_umuti={umuti} ≠ '
                                  f'umftth({umftth})+umftte({umftte})='
                                  f'{umftth + umftte}'))

    # ── ZPA005 : pcn_ftth ≠ somme pcn_ftth adresses ──────────────────
    if adresse_layer and has_field(layer, 'pcn_ftth'):
        ad_index = build_spatial_index(adresse_layer)
        for feature in layer.getFeatures():
            geom = feature.geometry()
            if geom is None or geom.isNull():
                continue
            fid = feature.id()
            did = get_display_id(feature, id_field)
            pcn_ftth = field_int(feature, 'pcn_ftth')
            if pcn_ftth is None:
                continue
            candidates = ad_index.intersects(geom.boundingBox())
            nb_ad = sum(
                field_int(adresse_layer.getFeature(cid), 'pcn_ftth') or 0
                for cid in candidates
                if adresse_layer.getFeature(cid).geometry() and
                geom.contains(adresse_layer.getFeature(cid).geometry())
            )
            if pcn_ftth != nb_ad:
                errors.append(err(fid, did, 'ZPA005', lname,
                                  'ZPA005 - pcn_ftth ≠ somme adresses',
                                  f'{did} : pcn_ftth={pcn_ftth} mais '
                                  f'somme pcn_ftth adresses={nb_ad}'))

    # ── ZPA008 : pcn_umftth ≠ somme PB ───────────────────────────────
    if pb_layer and has_field(layer, 'pcn_umftth') and \
            has_field(pb_layer, 'pcn_umftth'):
        pb_index = build_spatial_index(pb_layer)
        for feature in layer.getFeatures():
            geom = feature.geometry()
            if geom is None or geom.isNull():
                continue
            fid = feature.id()
            did = get_display_id(feature, id_field)
            pcn_um = field_int(feature, 'pcn_umftth')
            if pcn_um is None:
                continue
            candidates = pb_index.intersects(geom.boundingBox())
            sum_pb = sum(
                field_int(pb_layer.getFeature(cid), 'pcn_umftth') or 0
                for cid in candidates
                if pb_layer.getFeature(cid).geometry() and
                geom.contains(pb_layer.getFeature(cid).geometry())
            )
            if pcn_um != sum_pb:
                errors.append(err(fid, did, 'ZPA008', lname,
                                  'ZPA008 - pcn_umftth ≠ somme PB',
                                  f'{did} : pcn_umftth={pcn_um} mais '
                                  f'somme PB dans ZPA={sum_pb}'))
    return errors

# ─── ZPBO ─────────────────────────────────────────────────────────────────────

def check_zpbo(layer, zsro_layer, adresse_layer):
    """ZPB008 superpositions, ZPBO-FTTH, ZPBO-CAPA"""
    errors = []
    lname = layer.name()
    id_field = get_id_field(layer)
    features = list(layer.getFeatures())

    # ZPB008 : superpositions
    index = build_spatial_index(layer)
    checked = set()
    for f in features:
        geom = f.geometry()
        fid = f.id()
        if geom is None or geom.isNull():
            continue
        did = get_display_id(f, id_field)
        for cid in index.intersects(geom.boundingBox()):
            if cid == fid:
                continue
            pair = tuple(sorted([fid, cid]))
            if pair in checked:
                continue
            checked.add(pair)
            og = layer.getFeature(cid).geometry()
            if og and not og.isNull() and geom.overlaps(og):
                did2 = get_display_id(layer.getFeature(cid), id_field)
                errors.append(err(fid, did, 'ZPB008', lname,
                                  'ZPB008 - ZPBO superposées',
                                  f'{did} et {did2} : superposition'))

    # Containment ZSRO
    if zsro_layer:
        zsro_index = build_spatial_index(zsro_layer)
        for feature in features:
            geom = feature.geometry()
            if geom is None or geom.isNull():
                continue
            fid = feature.id()
            did = get_display_id(feature, id_field)
            candidates = zsro_index.intersects(geom.boundingBox())
            if not any(
                zsro_layer.getFeature(cid).geometry() and
                zsro_layer.getFeature(cid).geometry().contains(geom)
                for cid in candidates
            ):
                errors.append(err(fid, did, 'ZPBO-ZSRO', lname,
                                  'ZPBO hors ZSRO',
                                  f'{did} : ZPBO non contenue dans ZSRO'))

    # ZPBO-FTTH : pcn_ftth = somme pcn_ftth adresses
    if adresse_layer and has_field(layer, 'pcn_ftth'):
        ad_index = build_spatial_index(adresse_layer)
        for feature in features:
            geom = feature.geometry()
            if geom is None or geom.isNull():
                continue
            fid = feature.id()
            did = get_display_id(feature, id_field)
            pcn_ftth = field_int(feature, 'pcn_ftth')
            if pcn_ftth is None:
                continue
            candidates = ad_index.intersects(geom.boundingBox())
            sum_ad = sum(
                field_int(adresse_layer.getFeature(cid), 'pcn_ftth') or 0
                for cid in candidates
                if adresse_layer.getFeature(cid).geometry() and
                geom.contains(adresse_layer.getFeature(cid).geometry())
            )
            if pcn_ftth != sum_ad:
                errors.append(err(fid, did, 'ZPBO-FTTH', lname,
                                  'ZPBO-FTTH - pcn_ftth ≠ somme adresses',
                                  f'{did} : pcn_ftth={pcn_ftth} mais '
                                  f'somme adresses={sum_ad}'))

    # ZPBO-CAPA : zp_capamax selon pcn_ftth
    if has_field(layer, 'zp_capamax') and has_field(layer, 'pcn_ftth'):
        for feature in features:
            fid = feature.id()
            did = get_display_id(feature, id_field)
            ftth = field_int(feature, 'pcn_ftth')
            capa = field_int(feature, 'zp_capamax')
            if ftth is not None and capa is not None:
                expected = calc_capamax(ftth)
                if expected and capa != expected:
                    errors.append(err(fid, did, 'ZPBO-CAPA', lname,
                                      'ZPBO-CAPA - zp_capamax invalide',
                                      f'{did} : pcn_ftth={ftth} → '
                                      f'zp_capamax devrait être {expected}, '
                                      f'valeur: {capa}'))
    return errors


# ─── ZSRO ─────────────────────────────────────────────────────────────────────

def check_zsro(layer, zpa_layer, adresse_layer):
    """ZSRO005, ZSRO007, ZSRO009"""
    errors = []
    lname = layer.name()
    id_field = get_id_field(layer)

    for feature in layer.getFeatures():
        geom = feature.geometry()
        if geom is None or geom.isNull():
            continue
        fid = feature.id()
        did = get_display_id(feature, id_field)

        # ZSRO009 : zs_refpm format FI-XXXXX-XXXX (valide selon dictionnaire)
        if has_field(layer, 'zs_refpm'):
            refpm = field_val(feature, 'zs_refpm')
            # Format valide : FI-97307-0001
            if refpm and not re.match(r'^FI-\d{5}-\d+$', refpm):
                errors.append(err(fid, did, 'ZSRO009', lname,
                                  'ZSRO009 - zs_refpm mauvais format',
                                  f'{did} : zs_refpm="{refpm}" — '
                                  f'attendu FI-XXXXX-XXXX '
                                  f'(ex: FI-97307-0001)'))

        # ZSRO005 : pcn_ftth+pcn_ftte ≠ nb adresses
        if adresse_layer and has_field(layer, 'pcn_ftth'):
            pcn_ftth = field_int(feature, 'pcn_ftth') or 0
            pcn_ftte = field_int(feature, 'pcn_ftte') or 0 \
                if has_field(layer, 'pcn_ftte') else 0
            total_attr = pcn_ftth + pcn_ftte
            ad_index = build_spatial_index(adresse_layer)
            candidates = ad_index.intersects(geom.boundingBox())
            nb_ad = sum(
                (field_int(adresse_layer.getFeature(cid), 'pcn_ftth') or 0) +
                (field_int(adresse_layer.getFeature(cid), 'pcn_ftte') or 0)
                for cid in candidates
                if adresse_layer.getFeature(cid).geometry() and
                geom.contains(adresse_layer.getFeature(cid).geometry())
            )
            if total_attr != nb_ad and total_attr > 0:
                errors.append(err(fid, did, 'ZSRO005', lname,
                                  'ZSRO005 - pcn_ftth+ftte ≠ adresses',
                                  f'{did} : pcn_ftth+ftte={total_attr} '
                                  f'mais {nb_ad} dans la ZSRO'))

        # ZSRO007 : pcn_umtot = somme pcn_umftth des ZPA
        if zpa_layer and has_field(layer, 'pcn_umtot') and \
                has_field(zpa_layer, 'pcn_umftth'):
            pcn_umtot = field_int(feature, 'pcn_umtot')
            if pcn_umtot is not None:
                zpa_index = build_spatial_index(zpa_layer)
                candidates = zpa_index.intersects(geom.boundingBox())
                sum_um = sum(
                    field_int(zpa_layer.getFeature(cid), 'pcn_umftth') or 0
                    for cid in candidates
                    if zpa_layer.getFeature(cid).geometry() and
                    geom.contains(zpa_layer.getFeature(cid).geometry())
                )
                if pcn_umtot != sum_um:
                    errors.append(err(fid, did, 'ZSRO007', lname,
                                      'ZSRO007 - pcn_umtot ≠ somme ZPA',
                                      f'{did} : pcn_umtot={pcn_umtot} '
                                      f'mais somme pcn_umftth ZPA={sum_um}'))
    return errors


# ─── PEP_DI ───────────────────────────────────────────────────────────────────

def check_pep(layer, support_layer):
    """PEP-FORMAT, PEP sans support"""
    errors = []
    lname = layer.name()
    id_field = get_id_field(layer)
    sup_index = build_spatial_index(support_layer) if support_layer else None

    for feature in layer.getFeatures():
        fid = feature.id()
        did = get_display_id(feature, id_field)

        # PEP-FORMAT
        if has_field(layer, 'pcn_code'):
            code = field_val(feature, 'pcn_code')
            if code and not re.search(r'PEP_(TR|D1|D2)', code.upper()):
                errors.append(err(fid, did, 'PEP-FORMAT', lname,
                                  'PEP-FORMAT - pcn_code invalide',
                                  f'{did} : code "{code}" devrait '
                                  f'contenir PEP_TR, PEP_D1 ou PEP_D2'))

        # PEP sans support
        geom = feature.geometry()
        if geom is None or geom.isNull():
            continue
        if support_layer and sup_index:
            if not point_has_neighbor(
                    geom, support_layer, sup_index, SNAP_TOLERANCE):
                errors.append(err(fid, did, 'PEP-SUP', lname,
                                  'PEP sans support',
                                  f'{did} : aucun support aux '
                                  f'mêmes coordonnées'))
    return errors
def check_zpbo_rules(layer, zsro_layer, zpa_layer):
    """
    ZPBO-HORS-ZSRO  : une ZPBO dépasse la ZSRO
    ZPBO-MULTI-ZPA  : une ZPBO chevauche 2 ZPA différentes
    ZPBO-OVERLAP    : chevauchement entre 2 ZPBO
    ZPBO-TOUCH      : une ZPBO touche les limites de la ZSRO ou d'une ZPA
    """
    errors = []
    lname = layer.name()
    id_field = get_id_field(layer)
    features = list(layer.getFeatures())

    # Construire géométrie ZSRO
    zsro_geom = None
    if zsro_layer:
        zf = list(zsro_layer.getFeatures())
        if zf:
            zsro_geom = zf[0].geometry()
            for f in zf[1:]:
                zsro_geom = zsro_geom.combine(f.geometry())

    # Index ZPA
    zpa_index = build_spatial_index(zpa_layer) if zpa_layer else None

    # Index ZPBO pour chevauchements
    zpbo_index = build_spatial_index(layer)
    checked_pairs = set()

    for feat in features:
        geom = feat.geometry()
        if geom is None or geom.isNull():
            continue
        fid = feat.id()
        did = get_display_id(feat, id_field)

        # ── ZPBO-HORS-ZSRO ────────────────────────────────────────────
        if zsro_geom:
            if not zsro_geom.contains(geom):
                debord = geom.difference(zsro_geom)
                if debord and not debord.isEmpty():
                    errors.append(err(
                        fid, did, 'ZPBO-HORS-ZSRO', lname,
                        'ZPBO-HORS-ZSRO - ZPBO hors ZSRO',
                        f'{did} : une partie de la ZPBO est en dehors '
                        f'de la ZSRO'))

        # ── ZPBO-TOUCH : ne doit pas toucher ZSRO ou ZPA ──────────────
        if zsro_geom:
            if zsro_geom.touches(geom) or \
                    (not zsro_geom.contains(geom) and
                     zsro_geom.intersects(geom)):
                errors.append(err(
                    fid, did, 'ZPBO-TOUCH-ZSRO', lname,
                    'ZPBO-TOUCH-ZSRO - ZPBO touche limite ZSRO',
                    f'{did} : la ZPBO touche ou croise la limite '
                    f'de la ZSRO'))

        if zpa_layer and zpa_index:
            bbox = geom.boundingBox()
            zpa_candidates = zpa_index.intersects(bbox)
            zpa_containing = []
            for cid in zpa_candidates:
                zf = zpa_layer.getFeature(cid)
                zg = zf.geometry()
                if zg is None or zg.isNull():
                    continue
                if zg.contains(geom):
                    zpa_containing.append(cid)
                elif zg.touches(geom):
                    errors.append(err(
                        fid, did, 'ZPBO-TOUCH-ZPA', lname,
                        'ZPBO-TOUCH-ZPA - ZPBO touche limite ZPA',
                        f'{did} : la ZPBO touche la limite d\'une ZPA'))
                elif zg.intersects(geom) and not zg.contains(geom):
                    errors.append(err(
                        fid, did, 'ZPBO-MULTI-ZPA', lname,
                        'ZPBO-MULTI-ZPA - ZPBO sur 2 ZPA',
                        f'{did} : la ZPBO chevauche 2 ZPA differentes'))

            # ZPBO dans 2 ZPA
            if len(zpa_containing) > 1:
                errors.append(err(
                    fid, did, 'ZPBO-MULTI-ZPA', lname,
                    'ZPBO-MULTI-ZPA - ZPBO dans 2 ZPA',
                    f'{did} : la ZPBO est a cheval sur '
                    f'{len(zpa_containing)} ZPA differentes'))

        # ── ZPBO-OVERLAP : chevauchement entre ZPBO ───────────────────
        candidates = zpbo_index.intersects(geom.boundingBox())
        for cid in candidates:
            if cid == fid:
                continue
            pair = tuple(sorted([fid, cid]))
            if pair in checked_pairs:
                continue
            checked_pairs.add(pair)
            other = layer.getFeature(cid)
            og = other.geometry()
            if og is None or og.isNull():
                continue
            if geom.overlaps(og):
                did2 = get_display_id(other, id_field)
                errors.append(err(
                    fid, did, 'ZPBO-OVERLAP', lname,
                    'ZPBO-OVERLAP - Chevauchement ZPBO',
                    f'{did} et {did2} : les ZPBO se chevauchent'))

    return errors


def check_zpa_overlap(layer):
    """
    ZPA-OVERLAP : chevauchement entre 2 ZPA
    """
    errors = []
    lname = layer.name()
    id_field = get_id_field(layer)
    features = list(layer.getFeatures())
    index = build_spatial_index(layer)
    checked = set()

    for feat in features:
        geom = feat.geometry()
        fid = feat.id()
        if geom is None or geom.isNull():
            continue
        did = get_display_id(feat, id_field)
        for cid in index.intersects(geom.boundingBox()):
            if cid == fid:
                continue
            pair = tuple(sorted([fid, cid]))
            if pair in checked:
                continue
            checked.add(pair)
            og = layer.getFeature(cid).geometry()
            if og is None or og.isNull():
                continue
            if geom.overlaps(og):
                did2 = get_display_id(layer.getFeature(cid), id_field)
                errors.append(err(
                    fid, did, 'ZPA-OVERLAP', lname,
                    'ZPA-OVERLAP - Chevauchement ZPA',
                    f'{did} et {did2} : les ZPA se chevauchent'))
    return errors


def check_zsro_in_znro(zsro_layer, znro_layer):
    """
    ZSRO-HORS-ZNRO : la ZSRO n'est pas entierement dans la ZNRO
    """
    errors = []
    if not zsro_layer or not znro_layer:
        return errors
    lname = zsro_layer.name()
    id_field = get_id_field(zsro_layer)

    znro_feats = list(znro_layer.getFeatures())
    if not znro_feats:
        return errors
    znro_geom = znro_feats[0].geometry()
    for f in znro_feats[1:]:
        znro_geom = znro_geom.combine(f.geometry())

    for feat in zsro_layer.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isNull():
            continue
        did = get_display_id(feat, id_field)
        if not znro_geom.contains(geom):
            debord = geom.difference(znro_geom)
            if debord and not debord.isEmpty():
                errors.append(err(
                    feat.id(), did, 'ZSRO-HORS-ZNRO', lname,
                    'ZSRO-HORS-ZNRO - ZSRO hors ZNRO',
                    f'{did} : une partie de la ZSRO est en dehors '
                    f'de la ZNRO'))
    return errors


def check_aerien_rules(cb_layer, cm_layer):
    """
    AERIEN-MAX-CB  : plus de 3 CB_DI partageant la même géométrie d'un
                     cheminement CM_DI (uniquement cm_avct=C)
                     NB : si plusieurs CB_DI partagent un même POTEAU, c'est normal.
    AERIEN-LONG    : liaison aérienne CREATION > 40m (cm_avct=C)
    CONDUITE-400M  : CREATION_CONDUITE_DI (cm_avct=C) dépasse 400m sans support
    """
    errors = []
    if not cb_layer or not cm_layer:
        return errors

    AERIEN_VALS = ['AERIEN_ORANGE', 'AERIEN ORANGE',
                   'AERIEN_ENEDIS', 'AERIEN ENEDIS', 'CREATION_AERIEN']
    CONDUITE_VALS = ['CREATION_CONDUITE_DI']
    MAX_CB = 3
    MAX_LONG_AERIEN = 40.0
    MAX_CONDUITE_SANS_SUPPORT = 400.0
    TOLERANCE = 1.0
    OVERLAP_THRESHOLD = 0.80  # 80% de recouvrement géométrique pour "même cheminement"

    cb_id = get_id_field(cb_layer)
    cm_id = get_id_field(cm_layer)
    lname = cm_layer.name()

    cb_index = build_spatial_index(cb_layer)

    for cm_feat in cm_layer.getFeatures():
        cm_geom = cm_feat.geometry()
        if cm_geom is None or cm_geom.isNull():
            continue

        # Uniquement cm_avct = 'C' (Création)
        if has_field(cm_layer, 'cm_avct'):
            avct = field_val(cm_feat, 'cm_avct').upper().strip()
            if avct != 'C':
                continue

        pcn_sup = ''
        if has_field(cm_layer, 'pcn_sup'):
            pcn_sup = field_val(cm_feat, 'pcn_sup').upper().strip()

        is_aerien = any(a in pcn_sup for a in AERIEN_VALS)
        is_conduite_di = any(c in pcn_sup for c in CONDUITE_VALS)

        if not is_aerien and not is_conduite_di:
            continue

        cm_did = get_display_id(cm_feat, cm_id)
        cm_length = cm_geom.length()

        # ── AERIEN-LONG : longueur > 40m ──────────────────────────────
        if is_aerien:
            lng = 0.0
            if has_field(cm_layer, 'cm_long'):
                try:
                    lng = float(field_val(cm_feat, 'cm_long') or 0)
                except (ValueError, TypeError):
                    lng = cm_length
            else:
                lng = cm_length

            if lng > MAX_LONG_AERIEN:
                errors.append(err(
                    cm_feat.id(), cm_did, 'AERIEN-LONG', lname,
                    'AERIEN-LONG - Liaison aerienne trop longue',
                    f'{cm_did} ({pcn_sup}) : longueur={lng:.1f}m '
                    f'depasse la limite de {MAX_LONG_AERIEN}m '
                    f'(CREATION cm_avct=C)'))

            # ── AERIEN-MAX-CB : compter les CB_DI qui partagent la même
            #    géométrie du cheminement (pas juste un poteau commun)
            candidates = cb_index.intersects(cm_geom.boundingBox())
            cb_sur_cheminement = []
            for cid in candidates:
                cb_feat = cb_layer.getFeature(cid)
                cb_geom = cb_feat.geometry()
                if cb_geom is None or cb_geom.isNull():
                    continue
                if cb_geom.distance(cm_geom) > TOLERANCE:
                    continue
                # Vérifier que le câble suit réellement le cheminement
                # (pas seulement un point de passage commun = poteau)
                cb_len = cb_geom.length() if cb_geom.length() > 0 else 0
                cm_len = cm_length if cm_length > 0 else 1
                # Calculer la longueur de l'intersection géométrique
                try:
                    inter = cb_geom.intersection(cm_geom)
                    inter_len = inter.length() if inter and not inter.isNull() else 0
                except Exception:
                    inter_len = 0
                # Le câble partage le cheminement si l'intersection couvre
                # au moins OVERLAP_THRESHOLD de la longueur du CM ou du CB
                min_len = min(cb_len, cm_len)
                if min_len > 0 and inter_len / min_len >= OVERLAP_THRESHOLD:
                    cb_sur_cheminement.append(get_display_id(cb_feat, cb_id))
                elif inter_len > 5.0:
                    # Au moins 5m partagés (filtre les poteaux seuls)
                    cb_sur_cheminement.append(get_display_id(cb_feat, cb_id))

            if len(cb_sur_cheminement) > MAX_CB:
                errors.append(err(
                    cm_feat.id(), cm_did, 'AERIEN-MAX-CB', lname,
                    'AERIEN-MAX-CB - Trop de cables aeriens',
                    f'{cm_did} ({pcn_sup}) : {len(cb_sur_cheminement)} '
                    f'cables CB_DI partagent ce cheminement (max {MAX_CB}) — '
                    f'{", ".join(cb_sur_cheminement[:4])}'))

        # ── CONDUITE-400M : CREATION_CONDUITE_DI sans support à 400m ──
        # (vérification simplifiée sur la longueur déclarée ou géométrique)
        if is_conduite_di:
            lng = 0.0
            if has_field(cm_layer, 'cm_long'):
                try:
                    lng = float(field_val(cm_feat, 'cm_long') or 0)
                except (ValueError, TypeError):
                    lng = cm_length
            else:
                lng = cm_length

            if lng > MAX_CONDUITE_SANS_SUPPORT:
                errors.append(err(
                    cm_feat.id(), cm_did, 'CONDUITE-400M', lname,
                    'CONDUITE-400M - Conduite DI trop longue sans support',
                    f'{cm_did} ({pcn_sup}) : longueur={lng:.1f}m '
                    f'depasse {MAX_CONDUITE_SANS_SUPPORT}m sans support intermédiaire '
                    f'(CREATION_CONDUITE_DI cm_avct=C)'))

    return errors


def check_pb_engineering_rules(pb_layer, support_layer,
                                cm_layer, cb_layer):
    """
    PB-DOMAINE-PRIVE : PB en domaine prive (pt_prop=PRIVE)
    PB-POTEAU-MULTI  : plus de 3 boitiers PB sur un meme poteau
    PB6-AERIEN-OK    : PB6 sur aerien/facade = OK (pas d'erreur)
    PB12-DERIVE      : PB12 ne doit pas faire de derivation/piquage
    """
    errors = []
    if not pb_layer:
        return errors
    lname = pb_layer.name()
    id_field = get_id_field(pb_layer)
    sup_index = build_spatial_index(support_layer) if support_layer else None
    pb_index  = build_spatial_index(pb_layer)

    # Compter PB par support
    support_pb_count = {}

    for feat in pb_layer.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isNull():
            continue
        fid = feat.id()
        did = get_display_id(feat, id_field)
        pb_type = field_val(feat, 'pcn_pbtyp').upper() \
            if has_field(pb_layer, 'pcn_pbtyp') else ''

        # ── PB-DOMAINE-PRIVE ──────────────────────────────────────────
        if support_layer and sup_index and \
                has_field(support_layer, 'pt_prop'):
            bbox = geom.boundingBox()
            bbox.grow(SNAP_TOLERANCE)
            nearest = None
            min_d = float('inf')
            for cid in sup_index.intersects(bbox):
                sg = support_layer.getFeature(cid).geometry()
                if sg and not sg.isNull():
                    d = geom.distance(sg)
                    if d < min_d:
                        min_d = d
                        nearest = support_layer.getFeature(cid)
            if nearest and min_d <= SNAP_TOLERANCE:
                pt_prop = field_val(nearest, 'pt_prop').upper()
                if 'PRIVE' in pt_prop or 'PRIVÉ' in pt_prop:
                    errors.append(err(
                        fid, did, 'PB-DOMAINE-PRIVE', lname,
                        'PB-DOMAINE-PRIVE - PB en domaine prive',
                        f'{did} : PB positionne sur support de '
                        f'propriete privee ("{field_val(nearest, "pt_prop")}")'
                        f' — interdit sauf exception'))

                # Compter boitiers par support
                sup_code = field_val(nearest, 'pt_codeext') or \
                           f'fid={nearest.id()}'
                support_pb_count[sup_code] = \
                    support_pb_count.get(sup_code, 0) + 1

        # ── PB12-DERIVE : PB12 ne doit pas faire derivation ───────────
        if 'PB12' in pb_type:
            # Vérifier s'il y a plus de 2 câbles entrants/sortants
            if has_field(pb_layer, 'pcn_cb_ent'):
                cb_ent = field_int(feat, 'pcn_cb_ent')
                if cb_ent and cb_ent > 12:
                    errors.append(err(
                        fid, did, 'PB12-DERIVE', lname,
                        'PB12-DERIVE - PB12 avec derivation',
                        f'{did} : PB12 ne doit pas faire de '
                        f'derivation/piquage (pcn_cb_ent={cb_ent})'))

    # ── PB-POTEAU-MULTI : > 3 boitiers sur meme poteau ────────────────
    for sup_code, count in support_pb_count.items():
        if count > 3:
            errors.append(err(
                -1, sup_code, 'PB-POTEAU-MULTI',
                pb_layer.name(),
                'PB-POTEAU-MULTI - Trop de boitiers par poteau',
                f'Support {sup_code} : {count} boitiers PB detectes '
                f'(max 3 boitiers PBO par poteau Orange)'))

    return errors

# ─── Point d'entrée principal ──────────────────────────────────────────────────

def run_all_checks(layer, all_layers=None, tolerance=0.01):
    """Lance toutes les verifications selon le type et nom de la couche."""
    if not is_allowed_layer(layer):
        return []

    all_errors = []
    layer_name = layer.name().upper().strip()

    def get_layer(keyword, exclude=None):
        if not all_layers:
            return None
        for l in all_layers:
            n = l.name().upper().strip()
            if keyword in n:
                if exclude and any(e in n for e in exclude):
                    continue
                if is_allowed_layer(l):
                    return l
        return None

    support = get_layer('SUPPORT')

    # Verifications universelles
    # support transmis pour exclure les CB_DI intrasite (cb_long=0 sur support)
    all_errors += check_invalid_geometries(layer, support_layer=support)
    all_errors += check_multipart(layer)
    all_errors += check_missing_id(layer)
    all_errors += check_duplicates(layer, tolerance)
    # check_crossings supprime intentionnellement

    if not all_layers:
        return all_errors
    cb      = get_layer('CB_DI')
    cm      = get_layer('CM_DI')
    pb      = get_layer('PB',   exclude=['ZP'])
    pa      = get_layer('PA',   exclude=['ZP'])
    zsro    = get_layer('ZSRO')
    znro    = get_layer('ZNRO')
    zpa     = get_layer('ZPA')
    adresse = get_layer('ADRESSE')

    if 'ADRESSE' in layer_name:
        all_errors += check_adresse(layer)

    if 'CB_DI' in layer_name:
        all_errors += check_cbdi(layer, cm, support)

    if 'CM_DI' in layer_name:
        all_errors += check_cmdi(layer)
        # Règles aériennes (lancées depuis CM_DI)
        all_errors += check_aerien_rules(cb, layer)

    if 'NRO' in layer_name and 'ZNRO' not in layer_name:
        all_errors += check_nro(layer, support)

    if 'ZNRO' in layer_name:
        all_errors += check_znro(layer)

    if 'PA' in layer_name and 'ZP' not in layer_name:
        pass  # PA007 supprimé

    if 'PB' in layer_name and 'ZP' not in layer_name:
        all_errors += check_pb(layer, support, cb, cm)
        all_errors += check_pb_engineering_rules(
            layer, support, cm, cb)

    if 'SUPPORT' in layer_name:
        all_errors += check_support(layer, pb, pa, cb, cm)

    if 'ZPA' in layer_name and 'ZPBO' not in layer_name:
        all_errors += check_zpa(layer, zsro, pb, adresse)
        all_errors += check_zpa_overlap(layer)

    if 'ZPBO' in layer_name:
        all_errors += check_zpbo(layer, zsro, adresse)
        all_errors += check_zpbo_rules(layer, zsro, zpa)

    if 'ZSRO' in layer_name:
        all_errors += check_zsro(layer, zpa, adresse)
        # ZSRO dans ZNRO
        all_errors += check_zsro_in_znro(layer, znro)

    if 'PEP_DI' in layer_name or 'PEP' in layer_name:
        all_errors += check_pep(layer, support)

    return all_errors