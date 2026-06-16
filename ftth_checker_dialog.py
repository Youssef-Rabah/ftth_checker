import os
import json
import webbrowser
import tempfile
from datetime import datetime
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (QDialog, QTableWidgetItem, QMessageBox, 
                                  QCheckBox, QWidget, QHBoxLayout)
from qgis.PyQt.QtGui import QColor, QFont, QPixmap
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.core import QgsProject, QgsVectorLayer
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'ftth_checker_dialog.ui'))

PLUGIN_DIR = os.path.dirname(__file__)

ERROR_COLORS = {
    'geometrie nulle':                     QColor(252, 220, 220),
    'geometrie vide':                      QColor(252, 220, 220),
    'geometrie invalide':                  QColor(252, 220, 220),
    'multi-partie':                        QColor(255, 235, 200),
    'code manquant':                       QColor(255, 235, 200),
    'doublon exact':                       QColor(238, 237, 254),
    'pb001 - pb sans cm_di':               QColor(252, 220, 220),
    'pb sans support':                     QColor(252, 220, 220),
    'pb12 sur support interdit':           QColor(255, 180, 180),
    'pb12-forbid':                         QColor(255, 180, 180),
    'pb sans cb_di':                       QColor(252, 220, 220),
    'supp001 - support orphelin':          QColor(255, 235, 200),
    'hors zsro':                           QColor(238, 237, 254),
    'zpa hors zsro':                       QColor(238, 237, 254),
    'zpa-debord - zpa depasse zsro':       QColor(255, 220, 80),
    'zpa-trou - zone zsro non couverte':   QColor(255, 220, 80),
}

SECTION_COLORS = {
    'Geometrie':    QColor(220, 237, 200),
    'Adresse':      QColor(255, 245, 200),
    'Cables':       QColor(200, 230, 255),
    'Cheminements': QColor(210, 220, 255),
    'NRO':          QColor(230, 210, 255),
    'PB':           QColor(255, 210, 190),
    'Support':      QColor(255, 240, 180),
    'PEP':          QColor(200, 245, 230),
    'Zones':        QColor(220, 200, 255),
    'Autres':       QColor(220, 220, 220),
}

TYPE_TO_SECTION = {
    'geometrie nulle':                       'Geometrie',
    'geometrie vide':                        'Geometrie',
    'geometrie invalide':                    'Geometrie',
    'multi-partie':                          'Geometrie',
    'doublon exact':                         'Geometrie',
    'code manquant':                         'Geometrie',
    'ad001a - format ad_code invalide':      'Adresse',
    'ad013 - ad_postal manquant':            'Adresse',
    'ad015 - doublon adresse':               'Adresse',
    'ad-imb - pcn_imb incoherent':           'Adresse',
    'ad-ftth - pcn_ftth incoherent':         'Adresse',
    'cbdi009 - startpoint hors cm':          'Cables',
    'cbdi010 - endpoint hors cm':            'Cables',
    'cbdi011 - cl_nd1 startpoint':           'Cables',
    'cbdi012 - cl_nd2 endpoint':             'Cables',
    'cb-format - cl_codeext invalide':       'Cables',
    'cb-capafo - capacite invalide':         'Cables',
    'cb-long - cable trop long':             'Cables',
    'cb-long-zero - cable longueur 0 hors support': 'Cables',
    'cmdi005 - pcn_sup invalide':            'Cheminements',
    'cmdi009 - cm_compo manquant':           'Cheminements',
    'cm-avct - cm_avct invalide':            'Cheminements',
    'nro002 - nro sans support proche':      'NRO',
    'znro002 - zn_nroref non conforme':      'NRO',
    'pb001 - pb sans cm_di':                 'PB',
    'pb sans support':                       'PB',
    'pb12 sur support interdit':             'PB',
    'pb12-forbid':                           'PB',
    'pb sans cb_di':                         'PB',
    'pb-umftth - pcn_umftth invalide':       'PB',
    'pb016 - pcn_cb_ent invalide':           'PB',
    'pb017 - pcn_cb_ent invalide':           'PB',
    'pb-cbent - pcn_cb_ent invalide':        'PB',
    'supp001 - support orphelin':            'Support',
    'supp-type - pt_typephy invalide':       'Support',
    'pep-format - pcn_code invalide':        'PEP',
    'pep sans support':                      'PEP',
    'zpa hors zsro':                         'Zones',
    'hors zsro':                             'Zones',
    'zpa-debord - zpa depasse zsro':         'Zones',
    'zpa-trou - zone zsro non couverte':     'Zones',
    'zpa005 - pcn_ftth somme adresses':      'Zones',
    'zpa008 - pcn_umftth somme pb':          'Zones',
    'zpa-umtot - pcn_umtot incoherent':      'Zones',
    'zpa-umuti - pcn_umuti incoherent':      'Zones',
    'zpbo hors zsro':                        'Zones',
    'zpb008 - zpbo superposees':             'Zones',
    'zpbo-ftth - pcn_ftth somme adresses':   'Zones',
    'zpbo-capa - zp_capamax invalide':       'Zones',
    'zsro005 - pcn_ftth+ftte adresses':      'Zones',
    'zsro007 - pcn_umtot somme zpa':         'Zones',
    'zsro009 - zs_refpm mauvais format':     'Zones',
    'zpbo-hors-zsro - zpbo hors zsro':       'Zones',
    'zpbo-touch-zsro - zpbo touche limite zsro': 'Zones',
    'zpbo-touch-zpa - zpbo touche limite zpa':   'Zones',
    'zpbo-multi-zpa - zpbo sur 2 zpa':       'Zones',
    'zpbo-overlap - chevauchement zpbo':     'Zones',
    'zpa-overlap - chevauchement zpa':       'Zones',
    'zsro-hors-znro - zsro hors znro':       'Zones',
    'aerien-long - liaison aerienne trop longue': 'Cables',
    'aerien-max-cb - trop de cables aeriens':     'Cables',
    'conduite-400m - conduite di trop longue sans support': 'Cheminements',
    'pb-domaine-prive - pb en domaine prive':     'PB',
    'pb-poteau-multi - trop de boitiers par poteau': 'Support',
    'pb12-derive - pb12 avec derivation':         'PB',
}


class FtthCheckerDialog(QDialog, FORM_CLASS):

    def __init__(self, parent=None):
        super(FtthCheckerDialog, self).__init__(parent)
        self.setupUi(self)
        
        self.errors = []
        self.section_rows = {}
        self.section_header_rows = {}
        self.error_rows = []
        self.section_collapsed = {}

        self.auto_check_timer = QTimer()
        self.auto_check_timer.setInterval(3000)
        self.auto_check_timer.timeout.connect(self._auto_detect_corrections)

        # Connexions des boutons
        self.btnAnalyser.clicked.connect(self.analyser_projet)
        self.btnFermer.clicked.connect(self._on_close)
        self.btnRapport.clicked.connect(self.generer_rapport)
        self.tableResultats.cellClicked.connect(self._on_cell_clicked)

        # Configuration des en-têtes de colonnes
        self._setup_table_headers()

        # Label ZSRO + Projet
        from qgis.PyQt.QtWidgets import QLabel
        self.lblZsroProjet = QLabel('')
        self.lblZsroProjet.setAlignment(Qt.AlignCenter)
        self.lblZsroProjet.setStyleSheet(
            'font-size:15px;font-weight:bold;color:#3C3489;'
            'padding:4px 0px 0px 0px;letter-spacing:1px;')
        self.lblZsroProjet.setWordWrap(True)
        main_layout = self.layout()
        if main_layout:
            main_layout.insertWidget(1, self.lblZsroProjet)
        self._refresh_zsro_project_label()

        self._load_logos()

        # Style des boutons
        self.btnAnalyser.setStyleSheet(
            "QPushButton{background:#3C3489;color:white;font-weight:bold;"
            "padding:8px;border-radius:4px;font-size:14px;}"
            "QPushButton:hover{background:#534AB7;}")
        self.btnRapport.setStyleSheet(
            "QPushButton{background:#1565C0;color:white;font-weight:bold;"
            "padding:6px 14px;border-radius:4px;}"
            "QPushButton:hover{background:#1976D2;}")

        self._update_progress(0)
        self.lblFelicitation.setVisible(False)

    def _setup_table_headers(self):
        """Configure les noms et largeurs des colonnes du tableau"""
        headers = ["CORRECTION", "CODE", "COUCHE", "LIBELLÉ", "INFO"]
        self.tableResultats.setHorizontalHeaderLabels(headers)
        
        # Ajustement des largeurs
        self.tableResultats.setColumnWidth(0, 110)   # CORRECTION
        self.tableResultats.setColumnWidth(1, 95)    # CODE
        self.tableResultats.setColumnWidth(2, 110)   # COUCHE
        self.tableResultats.setColumnWidth(3, 260)   # LIBELLÉ
        self.tableResultats.setColumnWidth(4, 220)   # INFO
        
        self.tableResultats.horizontalHeader().setStretchLastSection(True)
        self.tableResultats.setTextElideMode(Qt.ElideRight)
        self.tableResultats.setSelectionMode(self.tableResultats.ExtendedSelection)
        self.tableResultats.setTextInteractionFlags = None  # pas applicable au tableau
        # Rendre les cellules sélectionnables et copiables via le menu contextuel
        self.tableResultats.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.tableResultats.setEditTriggers(self.tableResultats.NoEditTriggers)
        # Permettre la sélection de texte dans chaque cellule
        self.tableResultats.setSelectionBehavior(self.tableResultats.SelectItems)
        self.tableResultats.setHorizontalScrollMode(self.tableResultats.ScrollPerPixel)
        self.tableResultats.setVerticalScrollMode(self.tableResultats.ScrollPerPixel)
        self.tableResultats.setMinimumWidth(700)

    def _refresh_zsro_project_label(self):
        """Met à jour le label ZSRO + Projet en haut."""
        project = QgsProject.instance()
        project_name = project.title() or os.path.basename(
            project.fileName()).replace('.qgz', '').replace('.qgs', '')
        zsro_code = ''
        for l in project.mapLayers().values():
            if isinstance(l, QgsVectorLayer) and 'ZSRO' in l.name().upper():
                for feat in l.getFeatures():
                    try:
                        v = feat['zs_r4_code']
                        if v and str(v).strip() not in ('', 'NULL', 'None'):
                            zsro_code = str(v).strip()
                            break
                    except Exception:
                        try:
                            v = feat['zs_r4_code']
                            if v and str(v).strip() not in ('', 'NULL', 'None'):
                                zsro_code = str(v).strip()
                                break
                        except Exception:
                            pass
                if zsro_code:
                    break
        parts = []
        if zsro_code:
            parts.append('ZSRO : ' + zsro_code)
        if project_name:
            parts.append('Projet : ' + project_name)
        self.lblZsroProjet.setText('  |  '.join(parts) if parts else '')

    def _load_logos(self):
        for attr, filename, fallback_text, fallback_color in [
            ('lblLogoAmaris', 'Logo Amaris.png', 'Amaris', '#3C3489'),
            ('lblLogoOrange', 'Logo Orange.png', 'Orange', '#FF6600'),
        ]:
            label = getattr(self, attr)
            path = os.path.join(PLUGIN_DIR, filename)
            if os.path.exists(path):
                pix = QPixmap(path)
                pix = pix.scaled(140, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                label.setPixmap(pix)
                label.setFixedSize(pix.size())
            else:
                label.setText(fallback_text)
                label.setStyleSheet(f'font-weight:bold;color:{fallback_color};font-size:14px;')

    # ==================== Le reste du code (inchangé) ====================

    def _copy_table_selection(self):
        from qgis.PyQt.QtWidgets import QApplication
        selected = self.tableResultats.selectedRanges()
        if not selected:
            items = self.tableResultats.selectedItems()
            if items:
                text = '\t'.join(it.text() for it in items)
                QApplication.clipboard().setText(text)
            return
        rows_data = {}
        for rng in selected:
            for r in range(rng.topRow(), rng.bottomRow() + 1):
                row_texts = []
                for c in range(rng.leftColumn(), rng.rightColumn() + 1):
                    item = self.tableResultats.item(r, c)
                    row_texts.append(item.text() if item else '')
                rows_data[r] = rows_data.get(r, []) + row_texts
        text = '\n'.join('\t'.join(v) for v in rows_data.values())
        QApplication.clipboard().setText(text)

    # ── Utilitaires de sécurité C++ ──────────────────────────────────────
    @staticmethod
    def _is_layer_valid(layer):
        """Vérifie qu'un QgsVectorLayer C++ est toujours valide sans lever d'exception."""
        if layer is None:
            return False
        try:
            return layer.isValid()
        except RuntimeError:
            return False

    @staticmethod
    def _resolve_layer(layer_or_id):
        """
        Retourne un QgsVectorLayer valide ou None.
        Accepte un objet layer (vérifie qu'il est encore vivant) ou un ID (str).
        """
        try:
            if isinstance(layer_or_id, str):
                layer = QgsProject.instance().mapLayer(layer_or_id)
            else:
                layer = layer_or_id
                _ = layer.id()          # Sonde le pointeur C++
            return layer if (layer and layer.isValid()) else None
        except RuntimeError:
            return None

    def _get_all_vector_layers(self):
        return [l for l in QgsProject.instance().mapLayers().values()
                if isinstance(l, QgsVectorLayer)]

    def analyser_projet(self):
        from .geometry_checker import run_all_checks
        all_layers = self._get_all_vector_layers()
        if not all_layers:
            QMessageBox.warning(self, "Attention", "Aucune couche vectorielle chargée.")
            return

        self.errors = []
        self.section_rows = {}
        self.section_header_rows = {}
        self.section_collapsed = {}
        self.error_rows = []
        self.tableResultats.setRowCount(0)
        self.lblFelicitation.setVisible(False)
        self._refresh_zsro_project_label()

        for layer in all_layers:
            layer_errors = run_all_checks(layer, all_layers=all_layers)
            for e in layer_errors:
                e['layer_name'] = layer.name()
                e['layer_obj'] = layer
                e['layer_id'] = layer.id()   # ← ID stable pour résolution ultérieure
            self.errors += layer_errors

        if not self.errors:
            QMessageBox.information(self, "Résultat", "Aucune erreur détectée !")
            self._update_progress(100)
            return

        sections = {}
        for e in self.errors:
            key = e['type'].lower()
            section = TYPE_TO_SECTION.get(key, 'Autres')
            sections.setdefault(section, []).append(e)

        for section_name, section_errors in sections.items():
            self.section_collapsed[section_name] = False
            self._add_section_header(section_name, len(section_errors))
            for error in section_errors:
                self._add_error_row(error, section_name)

        self._draw_zpa_anomalies(all_layers)
        self._update_progress(0)
        self.auto_check_timer.start()

    def _add_section_header(self, section_name, count):
        row = self.tableResultats.rowCount()
        self.tableResultats.insertRow(row)
        color = SECTION_COLORS.get(section_name, QColor(220, 220, 220))
        arrow = '\u25B6' if self.section_collapsed.get(section_name) else '\u25BC'
        label = (arrow + '  ' + section_name + '  (' + str(count) +
                 ' erreur' + ('s' if count > 1 else '') + ')')
        item = QTableWidgetItem(label)
        item.setBackground(color)
        item.setFlags(Qt.ItemIsEnabled)
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        item.setFont(font)
        item.setData(Qt.UserRole, 'SECTION:' + section_name)
        self.tableResultats.setSpan(row, 0, 1, 5)
        self.tableResultats.setItem(row, 0, item)
        self.tableResultats.setRowHeight(row, 30)
        self.section_header_rows[section_name] = row
        self.section_rows.setdefault(section_name, [])

    def _add_error_row(self, error, section_name):
        row = self.tableResultats.rowCount()
        self.tableResultats.insertRow(row)

        chk = QCheckBox()
        chk.stateChanged.connect(lambda state, r=row: self._on_checkbox_changed(r, state))
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(chk)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tableResultats.setCellWidget(row, 0, container)

        color = ERROR_COLORS.get(error['type'].lower().replace('\u00e9', 'e')
                                                      .replace('\u00e8', 'e')
                                                      .replace('\u00ea', 'e')
                                                      .replace('\u00e0', 'a')
                                                      .replace('\u00f4', 'o'),
                                 QColor(255, 255, 255))

        for col, text in enumerate([
            error.get('leo_code', ''),
            error.get('layer_name', ''),
            error['type'],
            error['detail']
        ], start=1):
            item = QTableWidgetItem(text)
            item.setBackground(color)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setData(Qt.UserRole, error.get('fid'))
            self.tableResultats.setItem(row, col, item)

        self.section_rows.setdefault(section_name, []).append(row)
        self.error_rows.append({
            'row': row,
            'error': error,
            'layer': error.get('layer_obj'),
            'layer_id': error.get('layer_id'),   # ← ID stable
            'fid': error.get('fid'),
            'checked': False,
            'section': section_name,
        })

    def _on_cell_clicked(self, row, col):
        item = self.tableResultats.item(row, 0)
        if item is None:
            self._zoom_to_error(row, col)
            return
        data = item.data(Qt.UserRole)
        if isinstance(data, str) and data.startswith('SECTION:'):
            self._toggle_collapse(data.replace('SECTION:', ''))
        else:
            self._zoom_to_error(row, col)

    def _toggle_collapse(self, section_name):
        collapsed = not self.section_collapsed.get(section_name, False)
        self.section_collapsed[section_name] = collapsed
        header_row = self.section_header_rows.get(section_name)
        if header_row is not None:
            item = self.tableResultats.item(header_row, 0)
            if item:
                count = len(self.section_rows.get(section_name, []))
                arrow = '\u25B6' if collapsed else '\u25BC'
                label = (arrow + '  ' + section_name +
                         '  (' + str(count) +
                         ' erreur' + ('s' if count > 1 else '') + ')')
                item.setText(label)
        for r in self.section_rows.get(section_name, []):
            self.tableResultats.setRowHidden(r, collapsed)

    def _get_row_checked(self, row):
        widget = self.tableResultats.cellWidget(row, 0)
        if widget:
            chk = widget.findChild(QCheckBox)
            if chk:
                return chk.isChecked()
        return False

    def _update_row_style(self, row, checked):
        fg = QColor(150, 150, 150) if checked else QColor(0, 0, 0)
        for col in range(1, 5):
            item = self.tableResultats.item(row, col)
            if item:
                item.setForeground(fg)

    def _zoom_to_error(self, row, col):
        from qgis.utils import iface
        from qgis.core import QgsRectangle
        row_info = next(
            (r for r in self.error_rows if r['row'] == row), None)
        if not row_info:
            return
        fid = row_info.get('fid')
        if fid is None or fid < 0:
            return
        # Résoudre la couche de manière défensive : essayer l'objet puis l'ID
        layer = self._resolve_layer(row_info.get('layer'))
        if layer is None:
            layer = self._resolve_layer(row_info.get('layer_id', ''))
        if layer is None:
            return
        try:
            feature = layer.getFeature(fid)
            if not feature:
                return

            # ── Cas 1 : entité avec géométrie valide → zoom sur elle ──
            if feature.hasGeometry() and not feature.geometry().isNull() \
                    and not feature.geometry().isEmpty():
                bbox = feature.geometry().boundingBox()
                bbox.grow(max(bbox.width(), bbox.height()) * 0.5 + 10)
                iface.mapCanvas().setExtent(bbox)
                iface.mapCanvas().refresh()
                layer.selectByIds([fid])
                return

            # ── Cas 2 : entité SANS géométrie (GEOM001/GEOM002) ──────
            # On sélectionne quand même l'entité pour la mettre en évidence
            # dans la table attributaire, et on zoome sur l'étendue de la
            # couche entière comme repère visuel (centré sur la couche).
            layer.selectByIds([fid])
            extent = layer.extent()
            if extent and not extent.isNull() and extent.area() > 0:
                extent.grow(max(extent.width(), extent.height()) * 0.1 + 20)
                iface.mapCanvas().setExtent(extent)
                iface.mapCanvas().refresh()
            # Ouvrir la table attributaire filtrée sur l'entité sélectionnée
            # pour que l'utilisateur voie quelle ligne est concernée
            iface.showAttributeTable(layer)

        except RuntimeError:
            pass

    def _draw_zpa_anomalies(self, all_layers):
        from qgis.core import (QgsVectorLayer, QgsFeature,
                                QgsProject, QgsFillSymbol,
                                QgsSingleSymbolRenderer)
        from qgis.utils import iface

        def get_l(kw, exc=None):
            for l in all_layers:
                n = l.name().upper()
                if kw in n:
                    if exc and any(e in n for e in exc):
                        continue
                    # Vérifier que la couche est encore valide avant de la retourner
                    if self._is_layer_valid(l):
                        return l
            return None

        zpa_layer  = get_l('ZPA',  ['ZPBO'])
        zpbo_layer = get_l('ZPBO')
        zsro_layer = get_l('ZSRO')

        if not self._is_layer_valid(zsro_layer):
            return

        crs = zsro_layer.crs().authid()

        # Supprimer anciennes couches
        for old in ['Anomalie_ZPA', 'Anomalie_ZPBO', 'Anomalie_ZSRO']:
            for ol in QgsProject.instance().mapLayersByName(old):
                QgsProject.instance().removeMapLayer(ol.id())

        # ── Couche Anomalie_ZPA ───────────────────────────────────────
        zsro_feats = list(zsro_layer.getFeatures())

        if zsro_feats and self._is_layer_valid(zpa_layer):
            zsro_geom = zsro_feats[0].geometry()
            for zf in zsro_feats[1:]:
                zsro_geom = zsro_geom.combine(zf.geometry())

            zpa_anomalies = []  # list of (QgsFeature, type_str)

            # 1. ZPA qui dépasse la ZSRO
            for feat in zpa_layer.getFeatures():
                geom = feat.geometry()
                if geom and not zsro_geom.contains(geom):
                    d = geom.difference(zsro_geom)
                    if d and not d.isEmpty():
                        f = QgsFeature()
                        f.setGeometry(d)
                        zpa_anomalies.append((f, 'ZPA depasse ZSRO'))

            # 2. Zone ZSRO non couverte
            all_zpa = list(zpa_layer.getFeatures())
            if all_zpa:
                u = all_zpa[0].geometry()
                for zf in all_zpa[1:]:
                    g = zf.geometry()
                    if g and not g.isNull():
                        u = u.combine(g)
                trou = zsro_geom.difference(u)
                if trou and not trou.isEmpty() and trou.area() > 1.0:
                    f = QgsFeature()
                    f.setGeometry(trou)
                    zpa_anomalies.append((f, 'Zone ZSRO non couverte'))

            # 3. Chevauchements ZPA
            zpa_list = list(zpa_layer.getFeatures())
            from qgis.core import QgsSpatialIndex
            idx = QgsSpatialIndex()
            for zf in zpa_list:
                if zf.geometry() and not zf.geometry().isNull():
                    idx.addFeature(zf)
            checked = set()
            for zf in zpa_list:
                geom = zf.geometry()
                if not geom or geom.isNull():
                    continue
                for cid in idx.intersects(geom.boundingBox()):
                    if cid == zf.id():
                        continue
                    pair = tuple(sorted([zf.id(), cid]))
                    if pair in checked:
                        continue
                    checked.add(pair)
                    og = zpa_layer.getFeature(cid).geometry()
                    if og and not og.isNull() and geom.overlaps(og):
                        overlap = geom.intersection(og)
                        if overlap and not overlap.isEmpty():
                            f = QgsFeature()
                            f.setGeometry(overlap)
                            zpa_anomalies.append((f, 'Chevauchement ZPA'))

            if zpa_anomalies:
                zpa_anom_layer = QgsVectorLayer(
                    'Polygon?crs=' + crs + '&field=type_anomalie:string(80)'
                    '&field=surface_m2:double', 'Anomalie_ZPA', 'memory')
                enriched = []
                for (f, atype) in zpa_anomalies:
                    nf = QgsFeature(zpa_anom_layer.fields())
                    nf.setGeometry(f.geometry())
                    g = f.geometry()
                    area = g.area() if g and not g.isNull() else 0.0
                    nf['type_anomalie'] = atype
                    nf['surface_m2'] = round(area, 2)
                    enriched.append(nf)
                zpa_anom_layer.dataProvider().addFeatures(enriched)
                sym = QgsFillSymbol.createSimple({
                    'color': '255,220,0,160',
                    'outline_color': '255,140,0,255',
                    'outline_style': 'dash',
                    'outline_width': '1.0'})
                zpa_anom_layer.setRenderer(
                    QgsSingleSymbolRenderer(sym))
                QgsProject.instance().addMapLayer(zpa_anom_layer)

        # ── Couche Anomalie_ZPBO ──────────────────────────────────────
        # Rafraîchir zsro_geom si zsro_feats a été calculé ci-dessus
        if not zsro_feats:
            zsro_feats = list(zsro_layer.getFeatures()) if self._is_layer_valid(zsro_layer) else []
        if zsro_feats:
            zsro_geom = zsro_feats[0].geometry()
            for zf in zsro_feats[1:]:
                zsro_geom = zsro_geom.combine(zf.geometry())

        if self._is_layer_valid(zpbo_layer) and zsro_feats:
            zpbo_anomalies = []

            # 1. ZPBO hors ZSRO
            for feat in zpbo_layer.getFeatures():
                geom = feat.geometry()
                if geom and not zsro_geom.contains(geom):
                    d = geom.difference(zsro_geom)
                    if d and not d.isEmpty():
                        f = QgsFeature()
                        f.setGeometry(d)
                        zpbo_anomalies.append(f)

            # 2. Chevauchements ZPBO
            zpbo_list = list(zpbo_layer.getFeatures())
            from qgis.core import QgsSpatialIndex as QSI
            idx2 = QSI()
            for zf in zpbo_list:
                if zf.geometry() and not zf.geometry().isNull():
                    idx2.addFeature(zf)
            checked2 = set()
            for zf in zpbo_list:
                geom = zf.geometry()
                if not geom or geom.isNull():
                    continue
                for cid in idx2.intersects(geom.boundingBox()):
                    if cid == zf.id():
                        continue
                    pair = tuple(sorted([zf.id(), cid]))
                    if pair in checked2:
                        continue
                    checked2.add(pair)
                    og = zpbo_layer.getFeature(cid).geometry()
                    if og and not og.isNull() and geom.overlaps(og):
                        overlap = geom.intersection(og)
                        if overlap and not overlap.isEmpty():
                            f = QgsFeature()
                            f.setGeometry(overlap)
                            zpbo_anomalies.append(f)

            # 3. ZPBO sur 2 ZPA
            if self._is_layer_valid(zpa_layer):
                from qgis.core import QgsSpatialIndex as QSI2
                zpa_idx2 = QSI2()
                for zf in zpa_layer.getFeatures():
                    if zf.geometry() and not zf.geometry().isNull():
                        zpa_idx2.addFeature(zf)
                for feat in zpbo_layer.getFeatures():
                    geom = feat.geometry()
                    if not geom or geom.isNull():
                        continue
                    bbox = geom.boundingBox()
                    inter_zpa = [
                        cid for cid in zpa_idx2.intersects(bbox)
                        if (zpa_layer.getFeature(cid).geometry() and
                            zpa_layer.getFeature(cid).geometry()
                            .intersects(geom) and
                            not zpa_layer.getFeature(cid).geometry()
                            .contains(geom))
                    ]
                    if len(inter_zpa) >= 2:
                        for cid in inter_zpa:
                            og = zpa_layer.getFeature(cid).geometry()
                            part = geom.intersection(og)
                            if part and not part.isEmpty():
                                f = QgsFeature()
                                f.setGeometry(part)
                                zpbo_anomalies.append(f)

            if zpbo_anomalies:
                zpbo_anom_layer = QgsVectorLayer(
                    'Polygon?crs=' + crs + '&field=type_anomalie:string(80)'
                    '&field=surface_m2:double', 'Anomalie_ZPBO', 'memory')
                enriched_zpbo = []
                for i, f in enumerate(zpbo_anomalies):
                    nf = QgsFeature(zpbo_anom_layer.fields())
                    nf.setGeometry(f.geometry())
                    g = f.geometry()
                    area = g.area() if g and not g.isNull() else 0.0
                    nf['type_anomalie'] = 'Anomalie ZPBO'
                    nf['surface_m2'] = round(area, 2)
                    enriched_zpbo.append(nf)
                zpbo_anom_layer.dataProvider().addFeatures(enriched_zpbo)
                sym3 = QgsFillSymbol.createSimple({
                    'color': '255,100,0,160',
                    'outline_color': '200,50,0,255',
                    'outline_style': 'dash',
                    'outline_width': '1.0'})
                zpbo_anom_layer.setRenderer(
                    QgsSingleSymbolRenderer(sym3))
                QgsProject.instance().addMapLayer(zpbo_anom_layer)

        # ── Couche Anomalie_ZSRO (trous dans couverture ZPA) ─────────
        if (self._is_layer_valid(zsro_layer) and
                self._is_layer_valid(zpa_layer) and zsro_feats):
            for old in ['Anomalie_ZSRO']:
                for ol in QgsProject.instance().mapLayersByName(old):
                    QgsProject.instance().removeMapLayer(ol.id())
            zsro_anomalies = []
            all_zpa_f = list(zpa_layer.getFeatures())
            if all_zpa_f:
                union_zpa = all_zpa_f[0].geometry()
                for zf in all_zpa_f[1:]:
                    g = zf.geometry()
                    if g and not g.isNull():
                        union_zpa = union_zpa.combine(g)
                trou = zsro_geom.difference(union_zpa)
                if trou and not trou.isEmpty() and trou.area() > 1.0:
                    f2 = QgsFeature()
                    f2.setGeometry(trou)
                    zsro_anomalies.append(f2)
            if zsro_anomalies:
                zsro_anom_layer = QgsVectorLayer(
                    'Polygon?crs=' + crs + '&field=type_anomalie:string(80)'
                    '&field=surface_m2:double', 'Anomalie_ZSRO', 'memory')
                enriched_zsro = []
                for f2 in zsro_anomalies:
                    nf2 = QgsFeature(zsro_anom_layer.fields())
                    nf2.setGeometry(f2.geometry())
                    g2 = f2.geometry()
                    area2 = g2.area() if g2 and not g2.isNull() else 0.0
                    nf2['type_anomalie'] = 'Zone ZSRO non couverte par ZPA'
                    nf2['surface_m2'] = round(area2, 2)
                    enriched_zsro.append(nf2)
                zsro_anom_layer.dataProvider().addFeatures(enriched_zsro)
                from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer
                sym4 = QgsFillSymbol.createSimple({
                    'color': '100,100,255,120',
                    'outline_color': '50,50,200,255',
                    'outline_style': 'dash',
                    'outline_width': '1.2'})
                zsro_anom_layer.setRenderer(QgsSingleSymbolRenderer(sym4))
                QgsProject.instance().addMapLayer(zsro_anom_layer)

        iface.mapCanvas().refresh()
    def _auto_detect_corrections(self):
        changed = False
        valid_layer_ids = set(QgsProject.instance().mapLayers().keys())
        for row_info in self.error_rows:
            if row_info.get('checked'):
                continue
            fid   = row_info.get('fid')
            etype = row_info['error']['type'].lower()
            if fid is None or fid < 0:
                continue
            # Résoudre la couche : objet direct d'abord, puis par ID
            layer = self._resolve_layer(row_info.get('layer'))
            if layer is None:
                layer = self._resolve_layer(row_info.get('layer_id', ''))
            if layer is None:
                continue
            # Vérifier que l'ID est toujours dans le projet
            try:
                layer_id = layer.id()
            except RuntimeError:
                continue
            if layer_id not in valid_layer_ids:
                continue
            try:
                feature = layer.getFeature(fid)
            except RuntimeError:
                continue
            corrected = False
            if not feature.isValid():
                corrected = True
            else:
                geom = feature.geometry()
                if 'nulle' in etype or 'vide' in etype:
                    corrected = (geom and not geom.isNull()
                                 and not geom.isEmpty())
                elif 'invalide' in etype:
                    corrected = geom and geom.isGeosValid()
                elif 'multi' in etype:
                    corrected = (geom and (
                        not geom.isMultipart() or
                        len(geom.asGeometryCollection()) == 1))
                elif 'manquant' in etype:
                    from .geometry_checker import get_id_field
                    id_field = get_id_field(layer)
                    if id_field:
                        try:
                            val = str(feature[id_field]).strip()
                            corrected = val not in ('', 'NULL', 'None')
                        except Exception:
                            corrected = False
            if corrected:
                row = row_info['row']
                widget = self.tableResultats.cellWidget(row, 0)
                if widget:
                    chk = widget.findChild(QCheckBox)
                    if chk and not chk.isChecked():
                        chk.blockSignals(True)
                        chk.setChecked(True)
                        chk.blockSignals(False)
                        row_info['checked'] = True
                        self._update_row_style(row, True)
                        changed = True
        if changed:
            self._recalculate_progress()

    def _on_checkbox_changed(self, row, state):
        checked = (state == Qt.Checked)
        self._update_row_style(row, checked)
        for r in self.error_rows:
            if r['row'] == row:
                r['checked'] = checked
                break
        self._recalculate_progress()

    def _recalculate_progress(self):
        total = len(self.error_rows)
        if total == 0:
            self._update_progress(0)
            return
        checked = sum(1 for r in self.error_rows if r.get('checked', False))
        self._update_progress(int(checked * 100 / total))

    def _update_progress(self, pct):
        self.progressBar.setValue(pct)
        self.lblProgression.setText('Correction : ' + str(pct) + '%')
        if pct == 100:
            style = ("QProgressBar{border-radius:5px;text-align:center;}"
                     "QProgressBar::chunk{background:qlineargradient("
                     "x1:0,y1:0,x2:1,y2:0,stop:0 #1565C0,stop:1 #42A5F5);"
                     "border-radius:5px;}")
            self.lblFelicitation.setText(
                "Felicitations ! Toutes les erreurs sont corrigees. "
                "Vous pouvez poursuivre vers LEO.")
            self.lblFelicitation.setStyleSheet(
                "color:#1565C0;font-weight:bold;font-size:13px;"
                "padding:6px;background:#E3F2FD;border-radius:4px;")
            self.lblFelicitation.setVisible(True)
            self.auto_check_timer.stop()
        else:
            self.lblFelicitation.setVisible(False)
            if pct < 33:
                c1, c2 = '#C62828', '#E53935'
            elif pct < 50:
                c1, c2 = '#E53935', '#FF7043'
            elif pct < 66:
                c1, c2 = '#FF7043', '#FFA726'
            elif pct < 85:
                c1, c2 = '#FFA726', '#66BB6A'
            else:
                c1, c2 = '#66BB6A', '#2E7D32'
            style = (
                "QProgressBar{border-radius:5px;text-align:center;}"
                "QProgressBar::chunk{background:qlineargradient("
                "x1:0,y1:0,x2:1,y2:0,stop:0 " + c1 +
                ",stop:1 " + c2 + ");border-radius:5px;}")
        self.progressBar.setStyleSheet(style)

    def _build_spatial_index(self, layer):
        from qgis.core import QgsSpatialIndex
        idx = QgsSpatialIndex()
        if layer:
            for f in layer.getFeatures():
                if f.geometry() and not f.geometry().isNull():
                    idx.addFeature(f)
        return idx

    def _collect_context_data(self, all_layers):
        def get_l(kw, excl=None):
            for l in all_layers:
                n = l.name().upper().strip()
                if kw in n:
                    if excl and any(e in n for e in excl):
                        continue
                    return l
            return None

        def fv(feat, field):
            try:
                v = feat[field]
                return str(v).strip() if v is not None else ''
            except Exception:
                return ''

        def fi(feat, field):
            try:
                v = feat[field]
                if v is None or str(v).strip() in ('', 'NULL'):
                    return 0
                return int(float(str(v)))
            except Exception:
                return 0

        ctx = {}
        zsro_layer = get_l('ZSRO')
        ctx['zsro'] = {}
        if zsro_layer:
            feats = list(zsro_layer.getFeatures())
            if feats:
                f = feats[0]
                ctx['zsro'] = {
                    'code':         fv(f, 'zs_r4_code'),
                    'commune':      fv(f, 'zs_r2_code'),   # Commune PM
                    'nro_code':     fv(f, 'zs_r3_code'),   # Nom NRO
                    'budget_label': fv(f, 'zs_r4_code'),   # Label budget
                    'refpm':        fv(f, 'zs_refpm'),
                    'nd_code':      fv(f, 'zs_nd_code'),
                    'zn_code':      fv(f, 'zs_zn_code'),
                    'etatpm':       fv(f, 'zs_etatpm'),
                    'capamax':      fi(f, 'zs_capamax'),
                    'pcn_ftth':     fi(f, 'pcn_ftth'),
                    'pcn_ftte':     fi(f, 'pcn_ftte'),
                    'pcn_umtot':    fi(f, 'pcn_umtot'),
                    'comment':      fv(f, 'zs_comment'),
                }

        nro_layer = get_l('NRO', ['ZNRO'])
        ctx['nro_names'] = []
        if nro_layer:
            for f in nro_layer.getFeatures():
                code = fv(f, 'nd_code')
                if code:
                    ctx['nro_names'].append(code)

        zpa_layer  = get_l('ZPA', ['ZPBO'])
        zpbo_layer = get_l('ZPBO')
        ad_layer   = get_l('ADRESSE')
        sup_layer  = get_l('SUPPORT')
        pb_layer   = get_l('PB', ['ZP'])

        ctx['nb_zpa']      = zpa_layer.featureCount()  if zpa_layer  else 0
        ctx['nb_zpbo']     = zpbo_layer.featureCount() if zpbo_layer else 0
        ctx['nb_adresses'] = ad_layer.featureCount()   if ad_layer   else 0
        ctx['nb_supports'] = sup_layer.featureCount()  if sup_layer  else 0
        ctx['nb_pb']       = pb_layer.featureCount()   if pb_layer   else 0

        ctx['ad_comment']  = {}
        ctx['ad_imb']      = {'OUI': 0, 'NON': 0}
        ctx['ad_log_pro']  = {'log': 0, 'pro': 0}
        ctx['nb_bat_zpa']  = {}

        if ad_layer:
            zpa_idx = self._build_spatial_index(zpa_layer) \
                if zpa_layer else None
            for feat in ad_layer.getFeatures():
                cmt = fv(feat, 'ad_comment').upper() or 'N/A'
                ctx['ad_comment'][cmt] = \
                    ctx['ad_comment'].get(cmt, 0) + 1
                imb = fv(feat, 'pcn_imb').upper()
                if imb in ('OUI', 'NON'):
                    ctx['ad_imb'][imb] += 1
                ctx['ad_log_pro']['log'] += fi(feat, 'pcn_log')
                ctx['ad_log_pro']['pro'] += fi(feat, 'pcn_pro')
                if zpa_layer and zpa_idx:
                    geom = feat.geometry()
                    if geom and not geom.isNull():
                        for cid in zpa_idx.intersects(
                                geom.boundingBox()):
                            zf = zpa_layer.getFeature(cid)
                            zg = zf.geometry()
                            if zg and zg.contains(geom):
                                zcode = (fv(zf, 'pcn_code') or
                                         'fid=' + str(zf.id()))
                                ctx['nb_bat_zpa'][zcode] = \
                                    ctx['nb_bat_zpa'].get(zcode, 0) + 1
                                break

        ctx['sup_proptyp'] = {}
        ctx['sup_prop']    = {}
        if sup_layer:
            for feat in sup_layer.getFeatures():
                pt = fv(feat, 'pt_proptyp').upper() or 'N/A'
                if 'CST' in pt or 'CREATION' in pt:
                    key = 'A creer (CST)'
                elif 'OCC' in pt:
                    key = 'Occupe (OCC)'
                elif 'LOC' in pt:
                    key = 'Location (LOC)'
                else:
                    key = pt[:25] if pt else 'N/A'
                ctx['sup_proptyp'][key] = \
                    ctx['sup_proptyp'].get(key, 0) + 1
                pp = fv(feat, 'pt_prop').upper() or 'N/A'
                ctx['sup_prop'][pp] = ctx['sup_prop'].get(pp, 0) + 1

        ctx['pb_types'] = {}
        if pb_layer:
            for feat in pb_layer.getFeatures():
                t = fv(feat, 'pcn_pbtyp').upper() or 'N/A'
                if 'PB12' in t:
                    key = 'PB12'
                elif 'PBI' in t:
                    key = 'PBI'
                elif 'PBR' in t:
                    key = 'PB Reduit'
                elif 'PB6' in t:
                    key = 'PB6'
                else:
                    key = t[:15] if t else 'N/A'
                ctx['pb_types'][key] = ctx['pb_types'].get(key, 0) + 1

                # Prises (pcn_ftth) par ZPA
        ctx['nb_prises_zpa'] = {}
        if zpa_layer:
            for feat in zpa_layer.getFeatures():
                zcode = fv(feat, 'pcn_code') or 'fid=' + str(feat.id())
                ctx['nb_prises_zpa'][zcode] = fi(feat, 'pcn_ftth')# Prises (pcn_ftth) par ZPA
        ctx['nb_prises_zpa'] = {}
        if zpa_layer:
            for feat in zpa_layer.getFeatures():
                zcode = fv(feat, 'pcn_code') or 'fid=' + str(feat.id())
                ctx['nb_prises_zpa'][zcode] = fi(feat, 'pcn_ftth')

        return ctx

    def generer_rapport(self):
        if not self.errors:
            QMessageBox.warning(
                self, "Attention", "Lancez d'abord une analyse.")
            return

        project = QgsProject.instance()
        project_name = project.title() or os.path.basename(
            project.fileName()
        ).replace('.qgz', '').replace('.qgs', '')
        date_now = datetime.now().strftime('%d/%m/%Y %H:%M')

        all_layer_names = [
            l.name().upper()
            for l in project.mapLayers().values()]
        phase = 'APD' if any(
            'MOB_SUPPORT' in n or 'MOB_INFRA' in n
            for n in all_layer_names) else 'Maj APS'

        stats_couche = {}
        total_entites = {}
        for layer in project.mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                total_entites[layer.name()] = layer.featureCount()
        for e in self.errors:
            ln = e.get('layer_name', 'Inconnu')
            stats_couche[ln] = stats_couche.get(ln, 0) + 1

        # Nom ZSRO depuis zs_r4_code, NRO depuis zs_r3_code, commune depuis zs_r2_code
        zsro_label    = 'N/A'
        nro_label     = 'N/A'
        commune_label = 'N/A'
        for _lyr in project.mapLayers().values():
            if ('ZSRO' in _lyr.name().upper()
                    and isinstance(_lyr, QgsVectorLayer)):
                _feats = list(_lyr.getFeatures())
                if _feats:
                    _fz = _feats[0]
                    def _fv_safe(_feat, _fld):
                        try:
                            _v = _feat[_fld]
                            return str(_v).strip() if _v is not None else ''
                        except Exception:
                            return ''
                    _r4 = _fv_safe(_fz, 'zs_r4_code')
                    _r3 = _fv_safe(_fz, 'zs_r3_code')
                    _r2 = _fv_safe(_fz, 'zs_r2_code')
                    if _r4: zsro_label    = _r4
                    if _r3: nro_label     = _r3
                    if _r2: commune_label = _r2
                break

        error_geojson = self._build_error_geojson()
        total_err  = len(self.error_rows)
        corrected  = sum(1 for r in self.error_rows
                         if r.get('checked', False))
        pct_corr   = int(corrected * 100 / total_err) if total_err else 0

        stats_section = {}
        for e in self.errors:
            sec = TYPE_TO_SECTION.get(e['type'].lower(), 'Autres')
            stats_section[sec] = stats_section.get(sec, 0) + 1

        amaris_b64 = (self._img_to_base64('amaris logo white.png') or
                      self._img_to_base64('amaris logo white.PNG') or
                      self._img_to_base64('Logo Amaris.png'))
        orange_b64 = self._img_to_base64('Logo Orange.png')

        all_layers = self._get_all_vector_layers()
        ctx_data   = self._collect_context_data(all_layers)
        layers_geojson = self._build_layers_geojson(all_layers)
        budget_data    = self._collect_budget_data(all_layers)

        html = self._build_html(
            project_name=project_name,
            date_now=date_now,
            phase=phase,
            zsro_label=zsro_label,
            nro_label=nro_label,
            commune_label=commune_label,
            stats_couche=stats_couche,
            stats_section=stats_section,
            total_entites=total_entites,
            error_geojson=error_geojson,
            total_err=total_err,
            corrected=corrected,
            pct_correction=pct_corr,
            amaris_b64=amaris_b64,
            orange_b64=orange_b64,
            ctx_data=ctx_data,
            layers_geojson=layers_geojson,
            budget_data=budget_data,
        )

        tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix='.html', delete=False,
            encoding='utf-8', prefix='ftth_rapport_')
        tmp.write(html)
        tmp.close()
        webbrowser.open('file:///' + tmp.name)

    def _img_to_base64(self, filename):
        path = os.path.join(PLUGIN_DIR, filename)
        if not os.path.exists(path):
            return ''
        import base64
        with open(path, 'rb') as f:
            return 'data:image/png;base64,' + \
                   base64.b64encode(f.read()).decode()

# ═══════════════════════════════════════════════════════════════════
# PATCH — Nouvelles méthodes pour ftth_checker_dialog.py
# Ajouter ces 2 méthodes dans la classe FtthCheckerDialog,
# juste avant la méthode _build_error_geojson (ligne 1016)
# ═══════════════════════════════════════════════════════════════════

# ── MÉTHODE 1 : _build_layers_geojson ─────────────────────────────
# Génère le GeoJSON de toutes les couches livrables (pas uniquement
# les erreurs) pour affichage sur la carte web.

    def _build_layers_geojson(self, all_layers):
        """Exporte les couches livrables en GeoJSON pour la carte web."""
        LIVRABLE_KEYS = [
            'NRO', 'SRO', 'PA', 'PB', 'SUPPORT',
            'CB_DI', 'CM_DI', 'ZPA', 'ZPBO', 'ZSRO'
        ]
        LAYER_COLORS = {
            'NRO':     '#1e1a4a',
            'SRO':     '#3C3489',
            'PA':      '#1565C0',
            'PB':      '#E65100',
            'SUPPORT': '#F9A825',
            'CB_DI':   '#C62828',
            'CM_DI':   '#2E7D32',
            'ZPA':     '#6A1B9A',
            'ZPBO':    '#00838F',
            'ZSRO':    '#37474F',
        }

        result = {}
        crs_dst = QgsCoordinateReferenceSystem('EPSG:4326')
        # ── Import explicite de QgsGeometry (manquant = exception silencieuse) ──
        from qgis.core import QgsWkbTypes, QgsGeometry

        # Fids en erreur par couche
        error_fids = {}
        corrected_fids = {}
        for r in self.error_rows:
            ln_err = r['error'].get('layer_name', '')
            fid = r.get('fid', -1)
            if fid >= 0:
                error_fids.setdefault(ln_err, set()).add(fid)
                if r.get('checked', False):
                    corrected_fids.setdefault(ln_err, set()).add(fid)

        def _match_key(lname):
            """
            Associe un nom de couche QGIS (en majuscules) à une clé livrable.
            Ordre décroissant de spécificité pour éviter les faux positifs
            (ex: ZPA ne doit pas matcher ZPBO, PA ne doit pas matcher ZPA).
            Tolère les préfixes projets : MOB_ZPA, PZI_05_CB_DI, etc.
            """
            # Ordre : plus long d'abord pour éviter les chevauchements
            ORDERED = ['CB_DI', 'CM_DI', 'PEP_DI', 'ZPBO', 'ZSRO',
                       'ZPA', 'SRO', 'NRO', 'SUPPORT', 'PB', 'PA']
            for k in ORDERED:
                if k not in LIVRABLE_KEYS:
                    continue
                # Correspondance directe ou présence du mot-clé comme
                # segment délimité par _ ou en début/fin de chaîne
                if (lname == k
                        or lname.endswith('_' + k)
                        or lname.startswith(k + '_')
                        or ('_' + k + '_') in lname
                        or ('_' + k) in lname        # ← MOB_ZPA, MOB_PB …
                        or (k + '_') in lname):      # ← ZPA_LOT1 …
                    return k
            return None

        for layer in all_layers:
            lname = layer.name().upper().strip()

            # Exclure couches non livrables
            if any(x in lname for x in
                   ['CONDUITE_ORANGE', 'AERIEN_ENEDIS',
                    'AERIEN_ORANGE', 'ZNRO', 'CREATION_', 'ANOMALIE']):
                continue

            key = _match_key(lname)
            if key is None:
                continue

            # Fusionner si la clé existe déjà (plusieurs couches même type)
            existing_features = result.get(key, {}).get('features', [])
            features = list(existing_features)
            transform = QgsCoordinateTransform(
                layer.crs(), crs_dst, QgsProject.instance())

            # Tous les champs pour le popup (max 25)
            field_names = [f.name() for f in layer.fields()][:25]
            layer_name_str = layer.name()   # ← nom stable, pas de conflit

            for feat in layer.getFeatures():
                geom = feat.geometry()
                if not geom or geom.isNull():
                    continue
                try:
                    g = QgsGeometry(geom)   # ← QgsGeometry maintenant importé
                    try:
                        g.transform(transform)
                    except Exception:
                        g = QgsGeometry(geom)
                    gtype = QgsWkbTypes.geometryType(g.wkbType())

                    if gtype == QgsWkbTypes.PointGeometry:
                        if g.isMultipart():
                            c = g.centroid().asPoint()
                            geo = {'type': 'Point',
                                   'coordinates': [c.x(), c.y()]}
                        else:
                            pt = g.asPoint()
                            geo = {'type': 'Point',
                                   'coordinates': [pt.x(), pt.y()]}
                    elif gtype == QgsWkbTypes.LineGeometry:
                        if g.isMultipart():
                            lines_mp = g.asMultiPolyline()
                            geo = {'type': 'MultiLineString',
                                   'coordinates': [
                                       [[p.x(), p.y()] for p in seg]
                                       for seg in lines_mp]}
                        else:
                            line_pts = g.asPolyline()
                            geo = {'type': 'LineString',
                                   'coordinates': [
                                       [p.x(), p.y()] for p in line_pts]}
                    elif gtype == QgsWkbTypes.PolygonGeometry:
                        if g.isMultipart():
                            polys = g.asMultiPolygon()
                            geo = {'type': 'MultiPolygon',
                                   'coordinates': [
                                       [[[p.x(), p.y()] for p in ring]
                                        for ring in poly]
                                       for poly in polys]}
                        else:
                            poly = g.asPolygon()
                            geo = {'type': 'Polygon',
                                   'coordinates': [
                                       [[p.x(), p.y()] for p in ring]
                                       for ring in poly]}
                    else:
                        continue

                    fid = feat.id()
                    props = {fn: str(feat[fn]) if feat[fn] is not None
                             else '' for fn in field_names}
                    props['_layer'] = layer_name_str
                    props['_key'] = key
                    props['_color'] = LAYER_COLORS.get(key, '#555')
                    props['_fid'] = fid
                    is_err  = fid in error_fids.get(layer_name_str, set())
                    is_corr = fid in corrected_fids.get(layer_name_str, set())
                    props['_has_error'] = is_err
                    props['_corrected'] = is_corr
                    cx = g.centroid().asPoint()
                    props['_cx'] = cx.x()
                    props['_cy'] = cx.y()

                    features.append({
                        'type': 'Feature',
                        'geometry': geo,
                        'properties': props,
                    })
                except Exception:
                    continue

            if features:
                result[key] = {
                    'features': features,
                    'color': LAYER_COLORS.get(key, '#555'),
                    'type': int(QgsWkbTypes.geometryType(layer.wkbType())),
                }

        return json.dumps(result, ensure_ascii=False)


# ── MÉTHODE 2 : _collect_budget_data ──────────────────────────────
# Calcule les quantités pour l'estimation budgétaire.

    def _collect_budget_data(self, all_layers):
        """Calcule les quantités par élément pour le budget."""
        def get_l(kw, excl=None):
            for l in all_layers:
                n = l.name().upper().strip()
                if kw in n:
                    if excl and any(e in n for e in excl):
                        continue
                    return l
            return None

        def fv(feat, field):
            try:
                v = feat[field]
                return str(v).strip() if v is not None else ''
            except Exception:
                return ''

        def ff(feat, field):
            try:
                v = feat[field]
                if v is None or str(v).strip() in ('', 'NULL'):
                    return 0.0
                return float(str(v))
            except Exception:
                return 0.0

        cb_layer  = get_l('CB_DI')
        cm_layer  = get_l('CM_DI')
        pb_layer  = get_l('PB', ['ZP'])
        sup_layer = get_l('SUPPORT')
        zpa_layer = get_l('ZPA', ['ZPBO'])

        budget = {}

        # ── Câbles CB_DI ──────────────────────────────────────────
        long_di = 0.0
        long_tr = 0.0
        if cb_layer:
            for feat in cb_layer.getFeatures():
                lng = ff(feat, 'cb_long')
                typelog = fv(feat, 'cb_typelog').upper()
                if 'TR' in typelog:
                    long_tr += lng
                else:
                    long_di += lng
        budget['cable_di_m'] = round(long_di, 1)
        budget['cable_tr_m'] = round(long_tr, 1)

        # ── Cheminements CM_DI ────────────────────────────────────
        long_aerien_cst = 0.0
        long_cond_cst   = 0.0
        long_aerien_exi = 0.0
        nb_loc_poteau   = 0
        if cm_layer:
            for feat in cm_layer.getFeatures():
                lng    = ff(feat, 'cm_long')
                avct   = fv(feat, 'cm_avct').upper()
                pcnsup = fv(feat, 'pcn_sup').upper()
                if avct == 'C':
                    if 'AERIEN' in pcnsup:
                        long_aerien_cst += lng
                    elif 'CONDUITE' in pcnsup or 'CREATION' in pcnsup:
                        long_cond_cst += lng
                elif avct == 'E':
                    if 'AERIEN' in pcnsup:
                        long_aerien_exi += lng
                    if 'ENEDIS' in pcnsup:
                        nb_loc_poteau += 1
        budget['aerien_cst_m']   = round(long_aerien_cst, 1)
        budget['cond_cst_m']     = round(long_cond_cst, 1)
        budget['aerien_exi_m']   = round(long_aerien_exi, 1)
        budget['nb_loc_poteau']  = nb_loc_poteau
        # ── PA ────────────────────────────────────────────────────
        pa_layer = get_l('PA', excl=['ZP'])
        nb_pa = pa_layer.featureCount() if pa_layer else 0
        budget['nb_pa'] = nb_pa
        # ── PB ────────────────────────────────────────────────────
        nb_pb6 = nb_pb12 = nb_pbi = nb_pbr = 0
        if pb_layer:
            for feat in pb_layer.getFeatures():
                t = fv(feat, 'pcn_pbtyp').upper()
                if 'PBI' in t:
                    nb_pbi += 1
                elif 'PB12' in t:
                    nb_pb12 += 1
                elif 'PBR' in t:
                    nb_pbr += 1
                elif 'PB6' in t:
                    nb_pb6 += 1
        budget['nb_pb6']  = nb_pb6
        budget['nb_pb12'] = nb_pb12
        budget['nb_pbi']  = nb_pbi
        budget['nb_pbr']  = nb_pbr

        # ── Supports ──────────────────────────────────────────────
        nb_sup_cst = nb_facade = 0
        if sup_layer:
            for feat in sup_layer.getFeatures():
                pt = fv(feat, 'pt_proptyp').upper()
                nt = fv(feat, 'pcn_newsup').upper()
                if 'CST' in pt or 'CREATION' in pt:
                    if 'FACADE' in nt:
                        nb_facade += 1
                    else:
                        nb_sup_cst += 1
        budget['nb_sup_cst'] = nb_sup_cst
        budget['nb_facade']  = nb_facade

        # ── Coût par ZPA ──────────────────────────────────────────
        budget['cout_zpa'] = {}
        if zpa_layer and cb_layer:
            from qgis.core import QgsSpatialIndex
            cb_idx = QgsSpatialIndex()
            cb_feats = list(cb_layer.getFeatures())
            for f in cb_feats:
                if f.geometry() and not f.geometry().isNull():
                    cb_idx.addFeature(f)

            AVG_CABLE_DI = 2.4   # €/m moyen
            AVG_PB6      = 105   # €
            AVG_PB12     = 185   # €
            AVG_PBI      = 325   # €

            pb_idx = QgsSpatialIndex()
            pb_feats_list = []
            if pb_layer:
                pb_feats_list = list(pb_layer.getFeatures())
                for f in pb_feats_list:
                    if f.geometry() and not f.geometry().isNull():
                        pb_idx.addFeature(f)

            for zpa_feat in zpa_layer.getFeatures():
                zg = zpa_feat.geometry()
                if not zg or zg.isNull():
                    continue
                zcode = fv(zpa_feat, 'pcn_code') or 'fid=' + str(zpa_feat.id())
                # Câbles dans cette ZPA
                cable_m = 0.0
                for cid in cb_idx.intersects(zg.boundingBox()):
                    cf = cb_layer.getFeature(cid)
                    cg = cf.geometry()
                    if cg and zg.intersects(cg):
                        cable_m += ff(cf, 'cb_long')
                # PB dans cette ZPA
                zpa_pb6 = zpa_pb12 = zpa_pbi = 0
                if pb_layer:
                    for cid in pb_idx.intersects(zg.boundingBox()):
                        pf = pb_layer.getFeature(cid)
                        pg = pf.geometry()
                        if pg and zg.contains(pg):
                            t = fv(pf, 'pcn_pbtyp').upper()
                            if 'PBI' in t:
                                zpa_pbi += 1
                            elif 'PB12' in t:
                                zpa_pb12 += 1
                            else:
                                zpa_pb6 += 1
                cout = (cable_m * AVG_CABLE_DI +
                        zpa_pb6 * AVG_PB6 +
                        zpa_pb12 * AVG_PB12 +
                        zpa_pbi * AVG_PBI)
                budget['cout_zpa'][zcode] = round(cout, 0)

        return budget
    
    def _build_error_geojson(self):
        features = []
        seen = set()
        crs_dst = QgsCoordinateReferenceSystem('EPSG:4326')
        for row_info in self.error_rows:
            fid   = row_info.get('fid')
            error = row_info.get('error', {})
            if fid is None or fid < 0:
                continue
            # Résolution défensive de la couche
            layer = self._resolve_layer(row_info.get('layer'))
            if layer is None:
                layer = self._resolve_layer(row_info.get('layer_id', ''))
            if layer is None:
                continue
            key = (layer.name(), fid)
            if key in seen:
                continue
            seen.add(key)
            feature = layer.getFeature(fid)
            if not feature or not feature.hasGeometry():
                continue
            geom = feature.geometry()
            if geom.isNull():
                continue
            transform = QgsCoordinateTransform(
                layer.crs(), crs_dst, QgsProject.instance())
            try:
                geom_clone = QgsGeometry(geom)
                geom_clone.transform(transform)
                # Déterminer le type de géométrie
                from qgis.core import QgsWkbTypes
                gtype = QgsWkbTypes.geometryType(geom_clone.wkbType())
                if gtype == QgsWkbTypes.PointGeometry:
                    pt = geom_clone.asPoint()
                    geo_dict = {
                        'type': 'Point',
                        'coordinates': [pt.x(), pt.y()]
                    }
                    # Fallback centroid pour multi-points
                    if geom_clone.isMultipart():
                        c = geom_clone.centroid().asPoint()
                        geo_dict = {'type': 'Point',
                                    'coordinates': [c.x(), c.y()]}
                elif gtype == QgsWkbTypes.LineGeometry:
                    if geom_clone.isMultipart():
                        lines = geom_clone.asMultiPolyline()
                        geo_dict = {
                            'type': 'MultiLineString',
                            'coordinates': [
                                [[p.x(), p.y()] for p in ln]
                                for ln in lines
                            ]
                        }
                    else:
                        line = geom_clone.asPolyline()
                        geo_dict = {
                            'type': 'LineString',
                            'coordinates': [[p.x(), p.y()] for p in line]
                        }
                elif gtype == QgsWkbTypes.PolygonGeometry:
                    if geom_clone.isMultipart():
                        polys = geom_clone.asMultiPolygon()
                        geo_dict = {
                            'type': 'MultiPolygon',
                            'coordinates': [
                                [[[p.x(), p.y()] for p in ring]
                                 for ring in poly]
                                for poly in polys
                            ]
                        }
                    else:
                        poly = geom_clone.asPolygon()
                        geo_dict = {
                            'type': 'Polygon',
                            'coordinates': [
                                [[p.x(), p.y()] for p in ring]
                                for ring in poly
                            ]
                        }
                else:
                    c = geom_clone.centroid().asPoint()
                    geo_dict = {'type': 'Point',
                                'coordinates': [c.x(), c.y()]}

                # Centroid pour le clic de liste
                centroid = geom_clone.centroid().asPoint()
                features.append({
                    'type': 'Feature',
                    'geometry': geo_dict,
                    'properties': {
                        'layer':     layer.name(),
                        'code':      error.get('leo_code', ''),
                        'type':      error.get('type', ''),
                        'detail':    error.get('detail', ''),
                        'corrected': row_info.get('checked', False),
                        'section':   row_info.get('section', 'Autres'),
                        'cx':        centroid.x(),
                        'cy':        centroid.y(),
                    }
                })
            except Exception:
                pass
        return json.dumps(
            {'type': 'FeatureCollection', 'features': features},
            ensure_ascii=False)

    def _build_html(self, project_name, date_now, phase, zsro_label,
                    stats_couche, stats_section, total_entites,
                    error_geojson, total_err, corrected,
                    pct_correction, amaris_b64='', orange_b64='',
                    ctx_data=None, layers_geojson='{}',
                    budget_data=None, nro_label='N/A',
                    commune_label='N/A'):
        if budget_data is None:
            budget_data = {}
        if ctx_data is None:
            ctx_data = {}

        layers_labels  = json.dumps(list(stats_couche.keys()),
                                    ensure_ascii=False)
        layers_values  = json.dumps(list(stats_couche.values()))
        section_labels = json.dumps(list(stats_section.keys()),
                                    ensure_ascii=False)
        section_values = json.dumps(list(stats_section.values()))

        rows_html = ''
        for row_info in self.error_rows:
            e       = row_info['error']
            checked = row_info.get('checked', False)
            style   = ('opacity:0.45;text-decoration:line-through;'
                       if checked else '')
            status  = '\u2705' if checked else '\u274c'
            sec     = row_info.get('section', 'Autres')
            rows_html += (
                '<tr style="' + style + '" '
                'data-section="' + sec + '" '
                'data-corrected="' + str(checked).lower() + '">'
                '<td style="text-align:center">' + status + '</td>'
                '<td><span class="leo-badge">' +
                e.get('leo_code', '') + '</span></td>'
                '<td>' + e.get('layer_name', '') + '</td>'
                '<td>' + e.get('type', '') + '</td>'
                '<td style="max-width:350px;word-wrap:break-word">' +
                e.get('detail', '') + '</td>'
                '</tr>\n')

        amaris_img = (
            '<img src="' + amaris_b64 +
            '" style="height:44px;object-fit:contain;max-width:140px">'
            if amaris_b64 else
            '<span style="font-weight:700;color:#a5b4fc;'
            'font-size:16px">Amaris</span>')
        orange_img = (
            '<img src="' + orange_b64 +
            '" style="height:44px;object-fit:contain;max-width:140px">'
            if orange_b64 else
            '<span style="font-weight:700;color:#fdba74;'
            'font-size:16px">Orange</span>')

        unique_sections = list(dict.fromkeys(
            TYPE_TO_SECTION.get(e['type'].lower(), 'Autres')
            for e in self.errors))
        sec_btns = ''.join(
            '<button onclick="filterSec(\'' + s + '\',this)" '
            'class="filter-btn px-3 py-1 rounded-full text-xs '
            'border border-gray-300 hover:bg-indigo-600 '
            'hover:text-white transition">' + s + '</button>'
            for s in unique_sections)

        zsro = ctx_data.get('zsro', {})
        nro_names  = (zsro.get('nro_code', '')
                      or ', '.join(ctx_data.get('nro_names', []))
                      or nro_label or 'N/A')
        commune_pm = (zsro.get('commune', '') or commune_label or 'N/A')
        nb_zpa      = ctx_data.get('nb_zpa', 0)
        nb_zpbo     = ctx_data.get('nb_zpbo', 0)
        nb_adresses = ctx_data.get('nb_adresses', 0)

        ad_comment_j  = json.dumps(ctx_data.get('ad_comment', {}),
                                    ensure_ascii=False)
        ad_imb_j      = json.dumps(ctx_data.get('ad_imb', {}),
                                    ensure_ascii=False)
        ad_logpro_j   = json.dumps(ctx_data.get('ad_log_pro', {}),
                                    ensure_ascii=False)
        nb_bat_zpa_j  = json.dumps(ctx_data.get('nb_bat_zpa', {}),
                                    ensure_ascii=False)
        nb_prises_zpa_j = json.dumps(
            ctx_data.get('nb_prises_zpa', {}), ensure_ascii=False)
        sup_proptyp_j = json.dumps(ctx_data.get('sup_proptyp', {}),
                                    ensure_ascii=False)
        sup_prop_j    = json.dumps(ctx_data.get('sup_prop', {}),
                                    ensure_ascii=False)
        pb_types_j    = json.dumps(ctx_data.get('pb_types', {}),
                                    ensure_ascii=False)
        zsro_comment  = zsro.get('comment', '') or ''

        html = (
            '<!DOCTYPE html>\n'
            '<html lang="fr">\n'
            '<head>\n'
            '<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            '<title>Rapport FTTH - ' + project_name + '</title>\n'
            '<script src="https://cdn.tailwindcss.com"></script>\n'
'<script>tailwind.config={darkMode:"class"}</script>\n'
            '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>\n'
            '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>\n'
            '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>\n'
            '<script>\n'
            # Données
            'const COLORS=["#3C3489","#1565C0","#C62828","#E65100",'
            '"#F9A825","#2E7D32","#6A1B9A","#00838F","#4E342E","#37474F"];\n'
            'const errData=' + error_geojson + ';\n'
            'const allLayersData=' + layers_geojson + ';\n'
            'const budgetData=' + json.dumps(budget_data, ensure_ascii=False) + ';\n'
            'let map,osmL,satL,topoL;\n'
            'let mapReady=false,isDark=false;\n'
            'let leafletLayers={},currentFilter="all";\n'
            'let activeLayerKeys=new Set(Object.keys(allLayersData));\n'

            # Dark mode
            'function toggleDark(){\n'
            '  isDark=!isDark;\n'
            '  document.documentElement.classList.toggle("dark",isDark);\n'
            '  document.getElementById("themeBtn").innerHTML=isDark?"&#9728;":"&#127769;";\n'
            '  if(typeof Chart!=="undefined"){\n'
            '    Chart.defaults.color=isDark?"#d1d5db":"#374151";\n'
            '    Object.values(Chart.instances).forEach(c=>c.update());\n'
            '  }\n'
            '}\n'

            # Navigation
            'function showPage(name,btn){\n'
            '  document.querySelectorAll(".page,.map-page")'
            '.forEach(p=>p.classList.remove("active"));\n'
            '  document.querySelectorAll(".nav-btn")'
            '.forEach(b=>b.classList.remove("active"));\n'
            '  document.getElementById("page-"+name).classList.add("active");\n'
            '  btn.classList.add("active");\n'
            '  if(name==="map"&&!mapReady)initMap();\n'
            '  if(name==="budget")buildBudget();\n'
            '  if(name==="context")initContextCharts();\n'
            '}\n'

            # Chart.defaults est défini dans DOMContentLoaded
            'function mkChart(id,type,labels,data,colors,extra){\n'
            '  const el=document.getElementById(id);\n'
            '  if(!el)return;\n'
            '  new Chart(el,{type:type,'
            'data:{labels:labels,datasets:[{data:data,'
            'backgroundColor:colors||COLORS,'
            'borderRadius:type==="bar"?6:0,'
            'borderWidth:type==="doughnut"?2:0,'
            'hoverOffset:type==="doughnut"?8:0}]},'
            'options:Object.assign({responsive:true,'
            'plugins:{legend:{position:type==="doughnut"?"bottom":"none",'
            'display:type==="doughnut",'
            'labels:{font:{size:10},boxWidth:12}},'
            'tooltip:{callbacks:{label:(ctx)=>{\n'
            '  const t=ctx.dataset.data.reduce((a,b)=>a+b,0);\n'
            '  const p=t>0?Math.round(ctx.parsed/t*100):0;\n'
            '  return " "+ctx.label+" : "+ctx.formattedValue+" ("+p+"%)";}}}},'
            'scales:type!=="doughnut"?{y:{beginAtZero:true,ticks:{stepSize:1}}}:{}}'
            ',extra||{})});\n'
            '}\n'
            'function fmt(v){return new Intl.NumberFormat("fr-FR",'
            '{style:"currency",currency:"EUR",maximumFractionDigits:0}).format(v);}\n'
            'function kpi(lbl,val,cls){\n'
            '  return \'<div class="bg-white dark:bg-gray-800 rounded-xl p-4'
            ' text-center border border-gray-200 shadow-sm">\'+'
            '\'<div class="text-2xl font-bold \'+cls+\'">\'+val+\'</div>\'+'
            '\'<div class="text-xs text-gray-500 mt-1">\'+lbl+\'</div></div>\';\n'
            '}\n'

            # Carte Leaflet
            'function initMap(){\n'
            '  mapReady=true;\n'
            '  map=L.map("map",{zoomControl:true});\n'
            '  osmL=L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",'
            '{attribution:"© OpenStreetMap",maxZoom:19}).addTo(map);\n'
            '  satL=L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/'
            'World_Imagery/MapServer/tile/{z}/{y}/{x}",'
            '{attribution:"© Esri",maxZoom:19});\n'
            '  topoL=L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",'
            '{attribution:"© OpenTopoMap",maxZoom:17});\n'
            '  console.log("allLayersData keys:",Object.keys(allLayersData));\n'
'  console.log("allLayersData:",allLayersData);\n'
'  buildLayerToggles();\n'
'  renderAllLayers();\n'
            '}\n'

            # Basemap
            'function setBasemap(type){\n'
            '  [osmL,satL,topoL].forEach(l=>{if(l&&map.hasLayer(l))map.removeLayer(l);});\n'
            '  document.querySelectorAll(".tile-btn").forEach(b=>{'
            'b.classList.remove("bg-indigo-600","text-white");'
            'b.classList.add("border","border-gray-300");});\n'
            '  const id=type==="osm"?"btn-osm":type==="sat"?"btn-sat":"btn-topo";\n'
            '  document.getElementById(id).classList.add("bg-indigo-600","text-white");\n'
            '  (type==="osm"?osmL:type==="sat"?satL:topoL).addTo(map);\n'
            '}\n'

            # Layer toggles
            'function buildLayerToggles(){\n'
            '  const c=document.getElementById("layerToggles");\n'
            '  if(!c)return;\n'
            '  Object.keys(allLayersData).forEach(key=>{\n'
            '    const color=allLayersData[key].color;\n'
            '    const btn=document.createElement("button");\n'
            '    btn.className="text-xs px-2 py-0.5 rounded-full '
            'text-white font-medium";\n'
            '    btn.style.background=color;\n'
            '    btn.textContent=key;\n'
            '    btn.dataset.key=key;\n'
            '    btn.dataset.active="1";\n'
            '    btn.onclick=()=>toggleLayer(key,btn);\n'
            '    c.appendChild(btn);\n'
            '  });\n'
            '}\n'

            'function toggleLayer(key,btn){\n'
            '  if(activeLayerKeys.has(key)){\n'
            '    activeLayerKeys.delete(key);\n'
            '    btn.style.opacity="0.35";\n'
            '    if(leafletLayers[key]){'
            'leafletLayers[key].forEach(l=>map.removeLayer(l));'
            'leafletLayers[key]=[];}\n'
            '  }else{\n'
            '    activeLayerKeys.add(key);\n'
            '    btn.style.opacity="1";\n'
            '    renderLayer(key);\n'
            '  }\n'
            '  updateFeatList();\n'
            '}\n'

            # Filtre — 4 états : tout / erreurs / corrigées / corrects
            'function setMapFilter(f,btn){\n'
            '  currentFilter=f;\n'
            '  document.querySelectorAll(".map-filter")'
            '.forEach(b=>{\n'
            '    b.classList.remove("active","bg-indigo-600","text-white",'
            '"bg-red-600","bg-green-600","bg-blue-500","bg-gray-500");\n'
            '    b.classList.add("border","border-gray-300");\n'
            '  });\n'
            '  btn.classList.remove("border","border-gray-300");\n'
            '  if(f==="all")      btn.classList.add("active","bg-indigo-600","text-white");\n'
            '  else if(f==="errors")    btn.classList.add("active","bg-red-600","text-white");\n'
            '  else if(f==="corrected") btn.classList.add("active","bg-green-600","text-white");\n'
            '  else if(f==="ok")        btn.classList.add("active","bg-blue-500","text-white");\n'
            '  Object.keys(allLayersData).forEach(key=>{\n'
            '    if(leafletLayers[key]){'
            'leafletLayers[key].forEach(l=>map.removeLayer(l));'
            'leafletLayers[key]=[];}\n'
            '  });\n'
            '  activeLayerKeys.forEach(key=>renderLayer(key));\n'
            '  updateFeatList();\n'
            '}\n'

            # Render couche — toutes géométries, néon hover, filtre 3 états
            'function renderLayer(key){\n'
            '  if(!allLayersData[key])return;\n'
            '  const data=allLayersData[key];\n'
            '  const color=data.color;\n'
            '  leafletLayers[key]=leafletLayers[key]||[];\n'
            '  data.features.forEach(feat=>{\n'
            '    const p=feat.properties;\n'
            '    if(!feat.geometry||feat.geometry.type===undefined)return;\n'
            '    const hasErr=p._has_error;\n'
            '    const isCorr=p._corrected;\n'
            '    // Filtre : tout / erreurs / corrigees / corrects\n'
            '    if(currentFilter==="errors"&&(!hasErr||isCorr))return;\n'
            '    if(currentFilter==="corrected"&&!isCorr)return;\n'
            '    if(currentFilter==="ok"&&hasErr)return;\n'
            '    const strokeColor=hasErr?(isCorr?"#22c55e":"#ef4444"):color;\n'
            '    const fillColor  =hasErr?(isCorr?"#22c55e":"#ef4444"):color;\n'
            '    const gtype=feat.geometry.type;\n'
            '    const isPoly=gtype.includes("Polygon");\n'
            '    const isLine=gtype.includes("Line");\n'
            '    const isPoint=gtype.includes("Point");\n'
            '    // Styles normaux\n'
            '    const baseStyle={color:strokeColor,fillColor:fillColor,'
            'weight:hasErr?2.5:1.5,opacity:0.92,fillOpacity:isPoly?0.18:0};\n'
            '    // Styles néon au survol\n'
            '    const neonColor=hasErr?(isCorr?"#00ff88":"#ff2244"):color;\n'
            '    const neonStyle={\n'
            '      color:neonColor,fillColor:neonColor,\n'
            '      weight:isPoly?4:isLine?5:3,\n'
            '      opacity:1,fillOpacity:isPoly?0.38:0\n'
            '    };\n'
            '    try{\n'
            '      const geo=feat.geometry;\n'
            '      const gj=L.geoJSON({type:"Feature",geometry:geo},{\n'
            '        style:()=>({...baseStyle}),\n'
            '        pointToLayer:(f,ll)=>{\n'
            '          const mk=L.circleMarker(ll,{\n'
            '            radius:hasErr?9:6,\n'
            '            fillColor:fillColor,color:"#fff",\n'
            '            weight:2,fillOpacity:0.92,\n'
            '            className:"ftth-point-marker"\n'
            '          });\n'
            '          return mk;\n'
            '        }\n'
            '      });\n'
            '      const popupHtml=buildPopup(p,key,hasErr,isCorr);\n'
            '      gj.bindPopup(popupHtml,{maxWidth:340,className:"ftth-popup"});\n'
            '      // Effet néon au survol\n'
            '      gj.on("mouseover",function(e){\n'
            '        try{\n'
            '          if(isPoint){\n'
            '            e.layer.setStyle({radius:hasErr?13:10,'
            'fillColor:neonColor,color:neonColor,weight:3,fillOpacity:1});\n'
            '          } else {\n'
            '            this.setStyle(neonStyle);\n'
            '          }\n'
            '          // Ajouter classe CSS néon\n'
            '          const el=e.layer._path||e.layer._icon;\n'
            '          if(el)el.classList.add("neon-glow");\n'
            '          this.bringToFront();\n'
            '        }catch(ex){}\n'
            '      });\n'
            '      gj.on("mouseout",function(e){\n'
            '        try{\n'
            '          if(isPoint){\n'
            '            e.layer.setStyle({radius:hasErr?9:6,'
            'fillColor:fillColor,color:"#fff",weight:2,fillOpacity:0.92});\n'
            '          } else {\n'
            '            this.setStyle(baseStyle);\n'
            '          }\n'
            '          const el=e.layer._path||e.layer._icon;\n'
            '          if(el)el.classList.remove("neon-glow");\n'
            '        }catch(ex){}\n'
            '      });\n'
            '      gj.addTo(map);\n'
            '      leafletLayers[key].push(gj);\n'
            '    }catch(e){console.warn("renderLayer err",key,e);}\n'
            '  });\n'
            '}\n'

            'function renderAllLayers(){\n'
            '  const bounds=[];\n'
            '  activeLayerKeys.forEach(key=>{\n'
            '    renderLayer(key);\n'
            '    if(leafletLayers[key]){\n'
            '      leafletLayers[key].forEach(l=>{\n'
            '        try{const b=l.getBounds();'
            'if(b.isValid())bounds.push(b);}catch(e){}\n'
            '      });\n'
            '    }\n'
            '  });\n'
            '  if(bounds.length>0){\n'
            '    const combined=bounds.reduce('
            '(acc,b)=>acc.extend(b),bounds[0]);\n'
            '    map.fitBounds(combined.pad(0.05));\n'
            '  }else{map.setView([-12.8,45.15],11);}\n'
            '  updateFeatList();\n'
            '}\n'

            # Popup enrichi — tous les attributs + badge statut
            'function buildPopup(p,key,hasErr,isCorr){\n'
            '  const statusBadge=hasErr\n'
            '    ?(isCorr\n'
            '      ?\'<span class="ftth-badge badge-ok">&#10003; Corrige</span>\'\n'
            '      :\'<span class="ftth-badge badge-err">&#10007; Erreur</span>\')\n'
            '    :\'<span class="ftth-badge badge-conf">&#10004; Conforme</span>\';\n'
            '  // Couleur couche\n'
            '  const layerColor=allLayersData[key]?allLayersData[key].color:"#555";\n'
            '  // Séparer attributs métier des internes\n'
            '  const attrKeys=Object.keys(p).filter(k=>!k.startsWith("_"));\n'
            '  const mainField=attrKeys[0]||"";\n'
            '  const mainVal=mainField?p[mainField]:key;\n'
            '  // Construire lignes attributs\n'
            '  let rows="";\n'
            '  attrKeys.forEach(k=>{\n'
            '    const v=p[k];\n'
            '    const empty=(!v||v===""||v==="NULL"||v==="None");\n'
            '    if(empty)return;\n'  
            '    rows+=\'<tr>\'\n'
            '         +\'<td class="popup-key">\'+k+\'</td>\'\n'
            '         +\'<td class="popup-val">\'+v+\'</td>\'\n'
            '         +\'</tr>\';\n'
            '  });\n'
            '  if(!rows){\n'
            '    attrKeys.forEach(k=>{\n'
            '      rows+=\'<tr>\'\n'
            '           +\'<td class="popup-key">\'+k+\'</td>\'\n'
            '           +\'<td class="popup-val text-gray-400 italic">(vide)</td>\'\n'
            '           +\'</tr>\';\n'
            '    });\n'
            '  }\n'
            '  return `<div class="ftth-popup-inner">'
            '<div class="popup-header" style="background:${layerColor}">'
            '<span class="popup-layer-name">${key}</span>'
            '<span class="popup-main-val">${mainVal}</span>'
            '</div>'
            '<div class="popup-status">${statusBadge}</div>'
            '<div class="popup-table-wrap">'
            '<table class="popup-table">${rows}</table>'
            '</div></div>`;\n'
            '}\n'

            # Liste sidebar — affiche code entité + statut + couche
            'function updateFeatList(){\n'
            '  const list=document.getElementById("featList");\n'
            '  if(!list)return;\n'
            '  list.innerHTML="";\n'
            '  let total=0;\n'
            '  activeLayerKeys.forEach(key=>{\n'
            '    if(!allLayersData[key])return;\n'
            '    const layColor=allLayersData[key].color;\n'
            '    const feats=allLayersData[key].features;\n'
            '    // Tri : erreurs en premier\n'
            '    const sorted=[...feats].sort((a,b)=>{\n'
            '      const ae=a.properties._has_error?1:0;\n'
            '      const be=b.properties._has_error?1:0;\n'
            '      return be-ae;\n'
            '    });\n'
            '    sorted.forEach(feat=>{\n'
            '      const p=feat.properties;\n'
            '      const hasErr=p._has_error;\n'
            '      const isCorr=p._corrected;\n'
            '      if(currentFilter==="errors"&&(!hasErr||isCorr))return;\n'
            '      if(currentFilter==="corrected"&&!isCorr)return;\n'
            '      if(currentFilter==="ok"&&hasErr)return;\n'
            '      total++;\n'
            '      // Trouver le premier attribut métier non vide comme label\n'
            '      const metaKeys=Object.keys(p).filter(k=>!k.startsWith("_"));\n'
            '      let mainLabel="";\n'
            '      for(const mk of metaKeys){\n'
            '        const v=p[mk];\n'
            '        if(v&&v!==""&&v!=="NULL"&&v!=="None"){\n'
            '          mainLabel=v;break;\n'
            '        }\n'
            '      }\n'
            '      if(!mainLabel)mainLabel="fid="+p._fid;\n'
            '      // Statut visuel\n'
            '      const ic=hasErr?(isCorr?"✔":"✘"):"●";\n'
            '      const icColor=hasErr?(isCorr?"#22c55e":"#ef4444"):layColor;\n'
            '      const bgHover=hasErr?(isCorr?"#f0fdf4":"#fff1f2"):"#eff6ff";\n'
            '      const div=document.createElement("div");\n'
            '      div.style.cssText="padding:6px 10px;border-bottom:1px solid'
            ' #f3f4f6;cursor:pointer;transition:background .12s;";\n'
            '      div.innerHTML=\n'
            '        \'<div style="display:flex;align-items:center;gap:6px">\'\n'
            '        +\'<span style="color:\'+icColor+\';font-size:14px;font-weight:700">\'+ic+\'</span>\'\n'
            '        +\'<span style="font-size:10px;background:\'+layColor+\';color:white;\'\n'
            '        +\'padding:1px 7px;border-radius:10px;font-weight:700">\'+key+\'</span>\'\n'
            '        +\'<span style="font-size:11px;color:#374151;overflow:hidden;\'\n'
            '        +\'text-overflow:ellipsis;white-space:nowrap;max-width:160px" \'\n'
            '        +\'title="\'+mainLabel+\'">\'+mainLabel+\'</span>\'\n'
            '        +\'</div>\';\n'
            '      div.onmouseover=()=>div.style.background=bgHover;\n'
            '      div.onmouseout=()=>div.style.background="";\n'
            '      div.onclick=()=>{\n'
            '        const cx=p._cx,cy=p._cy;\n'
            '        if(cx&&cy){map.setView([cy,cx],18);}\n'
            '      };\n'
            '      list.appendChild(div);\n'
            '    });\n'
            '  });\n'
            '  const ec=document.getElementById("errCount");\n'
            '  if(ec)ec.textContent=total;\n'
            '}\n'

            # Budget
            'let budgetBuilt=false;\n'
            'function buildBudget(){\n'
            '  if(budgetBuilt)return;\n'
            '  budgetBuilt=true;\n'
            '  const d=budgetData;\n'
            '  const AVG={cable_di:2.4,cable_tr:10,aerien_cst:52.5,'
            'aerien_exi:5,cond:80,facade:27.5,sup:100,'
            'loc_poteau:16.5,pb6:105,pb12:185,pbi:325,pbr:105};\n'
            '  const items=[\n'
            '    {grp:"Cables",label:"Cable DI/D2 ("+d.cable_di_m+"m)",'
            'min:0.8,max:4,unit:"€/m",qty:d.cable_di_m},'
            '    {grp:"Cables",label:"Cable Transport ("+d.cable_tr_m+"m)",'
            'min:5,max:15,unit:"€/m",qty:d.cable_tr_m},'
            '    {grp:"GC",label:"Cheminement aerien creation ("+d.aerien_cst_m+"m)",'
            'min:25,max:80,unit:"€/m",qty:d.aerien_cst_m},'
            '    {grp:"GC",label:"Cheminement aerien reutilisation ("+d.aerien_exi_m+"m)",'
            'min:2,max:8,unit:"€/m",qty:d.aerien_exi_m},'
            '    {grp:"GC",label:"Conduite souterraine creation ("+d.cond_cst_m+"m)",'
            'min:30,max:120,unit:"€/m",qty:d.cond_cst_m},'
            '    {grp:"Points Techniques",label:"PA ("+d.nb_pa+" unites)",'
            'min:150,max:400,unit:"€/u",qty:d.nb_pa},'
            '    {grp:"Points Techniques",label:"PB6 ("+d.nb_pb6+" unites)",'
            'min:60,max:150,unit:"€/u",qty:d.nb_pb6},'
            '    {grp:"Points Techniques",label:"PB12 ("+d.nb_pb12+" unites)",'
            'min:120,max:250,unit:"€/u",qty:d.nb_pb12},'
            '    {grp:"Points Techniques",label:"PBI ("+d.nb_pbi+" unites)",'
            'min:150,max:500,unit:"€/u",qty:d.nb_pbi},'
            '    {grp:"Points Techniques",label:"PB Reduit ("+d.nb_pbr+" unites)",'
            'min:60,max:150,unit:"€/u",qty:d.nb_pbr},'
            '    {grp:"Supports",label:"Support a creer ("+d.nb_sup_cst+" unites)",'
            'min:50,max:200,unit:"€/u",qty:d.nb_sup_cst},'
            '    {grp:"Supports",label:"Ancrage facade ("+d.nb_facade+" unites)",'
            'min:15,max:40,unit:"€/u",qty:d.nb_facade},'
            '    {grp:"Location",label:"Location poteau ENEDIS ("+d.nb_loc_poteau+" poteaux/an)",'
            'min:8,max:25,unit:"€/u/an",qty:d.nb_loc_poteau},'
            '  ];\n'
            '  let totalMin=0,totalMax=0,totalMoy=0;\n'
            '  const groups={};\n'
            '  items.forEach(it=>{\n'
            '    const avg=(it.min+it.max)/2;\n'
            '    const totMin=it.min*it.qty;\n'
            '    const totMax=it.max*it.qty;\n'
            '    const totMoy=avg*it.qty;\n'
            '    totalMin+=totMin;totalMax+=totMax;totalMoy+=totMoy;\n'
            '    if(!groups[it.grp])groups[it.grp]={items:[],min:0,max:0,moy:0};\n'
            '    groups[it.grp].items.push({...it,avg,totMin,totMax,totMoy});\n'
            '    groups[it.grp].min+=totMin;\n'
            '    groups[it.grp].max+=totMax;\n'
            '    groups[it.grp].moy+=totMoy;\n'
            '  });\n'
            'const grpColors={"Cables":"#3C3489","GC":"#1565C0",'
            '"Points Techniques":"#E65100","Supports":"#F9A825",'
            '"Location":"#2E7D32"};\n'
            '  let html=\'<div class="grid grid-cols-3 gap-4 mb-5">\';\n'
            '  html+=kpi("Estimation basse",fmt(totalMin),"text-blue-600");\n'
            '  html+=kpi("Estimation moyenne",fmt(totalMoy),"text-green-700");\n'
            '  html+=kpi("Estimation haute",fmt(totalMax),"text-red-600");\n'
            '  html+=\'</div>\';\n'
            '  Object.keys(groups).forEach(grp=>{\n'
            '    const g=groups[grp];\n'
            '    const gc=grpColors[grp]||"#555";\n'
            '    html+=\'<div class="mb-4 rounded-xl border border-gray-200'
            ' dark:border-gray-700 overflow-hidden shadow-sm">\';\n'
            '    html+=\'<div style="background:\'+gc+\'" class="px-4 py-2'
            ' flex justify-between items-center text-white">\';\n'
            '    html+=\'<span class="font-bold text-sm">\'+grp+\'</span>\';\n'
            '    html+=\'<span class="text-xs bg-white/20 px-2 py-0.5'
            ' rounded-full">Moy. \'+fmt(g.moy)+\'</span></div>\';\n'
            '    html+=\'<table class="w-full text-xs">\';\n'
            '    html+=\'<thead><tr class="bg-gray-50 dark:bg-gray-700">\';\n'
            '    html+=\'<th class="text-left p-2">Element</th>\';\n'
            '    html+=\'<th class="p-2">Unite</th>\';\n'
            '    html+=\'<th class="p-2">Qte</th>\';\n'
            '    html+=\'<th class="p-2">Cout min (€)</th>\';\n'
            '    html+=\'<th class="p-2">Cout moy (€)</th>\';\n'
            '    html+=\'<th class="p-2">Cout max (€)</th></tr></thead>\';\n'
            '    html+=\'<tbody>\';\n'
            '    g.items.forEach(it=>{\n'
            '      html+=\'<tr class="border-t border-gray-100'
            ' dark:border-gray-700 hover:bg-gray-50">\';\n'
            '      html+=\'<td class="p-2">\'+it.label+\'</td>\';\n'
            '      html+=\'<td class="p-2 text-center text-gray-500">\'+it.unit+\'</td>\';\n'
            '      html+=\'<td class="p-2 text-center font-medium">\'+it.qty+\'</td>\';\n'
            '      html+=\'<td class="p-2 text-center text-blue-600">\'+fmt(it.totMin)+\'</td>\';\n'
            '      html+=\'<td class="p-2 text-center font-bold text-green-700">\'+fmt(it.totMoy)+\'</td>\';\n'
            '      html+=\'<td class="p-2 text-center text-red-600">\'+fmt(it.totMax)+\'</td>\';\n'
            '      html+=\'</tr>\';\n'
            '    });\n'
            '    html+=\'</tbody></table></div>\';\n'
            '  });\n'
            # Coût par ZPA
            '  const coutZpa=' + json.dumps(
                budget_data.get('cout_zpa', {}),
                ensure_ascii=False) + ';\n'
            '  if(Object.keys(coutZpa).length>0){\n'
            '    html+=\'<div class="mt-4 bg-white dark:bg-gray-800'
            ' rounded-xl border border-gray-200 dark:border-gray-700'
            ' shadow-sm overflow-hidden">\';\n'
            '    html+=\'<div class="bg-purple-700 px-4 py-2 text-white'
            ' font-bold text-sm">Estimation par ZPA</div>\';\n'
            '    html+=\'<table class="w-full text-xs"><thead>\';\n'
            '    html+=\'<tr class="bg-gray-50 dark:bg-gray-700">\';\n'
            '    html+=\'<th class="text-left p-2">ZPA</th>\';\n'
            '    html+=\'<th class="p-2">Cout estimatif moyen (€)</th></tr>\';\n'
            '    html+=\'</thead><tbody>\';\n'
            '    let totalZpa=0;\n'
            '    Object.entries(coutZpa).forEach(([zpa,cout])=>{\n'
            '      totalZpa+=cout;\n'
            '      html+=\'<tr class="border-t border-gray-100 hover:bg-gray-50">\';\n'
            '      html+=\'<td class="p-2 font-medium">\'+zpa+\'</td>\';\n'
            '      html+=\'<td class="p-2 text-center font-bold'
            ' text-green-700">\'+fmt(cout)+\'</td></tr>\';\n'
            '    });\n'
            '    html+=\'<tr class="bg-purple-50 dark:bg-purple-900/20'
            ' border-t-2 border-purple-300">\';\n'
            '    html+=\'<td class="p-2 font-bold text-purple-800'
            ' dark:text-purple-300">TOTAL ZSRO</td>\';\n'
            '    html+=\'<td class="p-2 text-center font-bold text-xl'
            ' text-purple-800 dark:text-purple-300">\'+fmt(totalZpa)+\'</td></tr>\';\n'
            '    html+=\'</tbody></table></div>\';\n'
            '  }\n'
            # Tuile total
            '  html+=\'<div class="mt-5 bg-gradient-to-r from-green-600'
            ' to-teal-600 text-white rounded-xl p-6 text-center shadow-xl">\';\n'
            '  html+=\'<div class="text-sm font-semibold opacity-90 mb-1">'
            'Cout estimatif total de deploiement FTTH — ZSRO ' + zsro_label + '</div>\';\n'
            '  html+=\'<div class="text-4xl font-bold mb-1">\'+fmt(totalMoy)+\'</div>\';\n'
            '  html+=\'<div class="text-sm opacity-80">Fourchette : \'+fmt(totalMin)+'
            '\'  —  \'+fmt(totalMax)+\'</div></div>\';\n'
            '  document.getElementById("budgetContent").innerHTML=html;\n'
            '}\n'

            # Filtre tableau
            'function filterSec(section,btn){\n'
            '  document.querySelectorAll(".filter-btn")'
            '.forEach(b=>b.classList.remove("active"));\n'
            '  btn.classList.add("active");\n'
            '  document.querySelectorAll("#errTableBody tr").forEach(tr=>{\n'
            '    tr.style.display='
            '(section==="all"||tr.dataset.section===section)?"":"none";\n'
            '  });\n'
            '}\n'
            '</script>\n'
            '<style>\n'
            '.page{display:none}.page.active{display:block}\n'
            '.map-page{display:none}.map-page.active{display:flex;height:calc(100vh - 100px)}\n'
            '#map{flex:1;min-height:400px}\n'
            '.nav-btn{opacity:.65;border-bottom:3px solid transparent;transition:.15s}\n'
            '.nav-btn.active{opacity:1;border-bottom-color:#fff}\n'
            '.filter-btn.active{background:#3C3489;color:#fff;border-color:#3C3489}\n'
            '.gauge-bar{background:#e5e7eb;border-radius:9999px;height:12px;overflow:hidden}\n'
            '.gauge-fill{height:100%;background:linear-gradient(90deg,#3C3489,#1565C0);'
            'border-radius:9999px;transition:width .4s}\n'
            '.leo-badge{background:#EEF2FF;color:#3C3489;padding:2px 8px;'
            'border-radius:12px;font-size:10px;font-weight:700;font-family:monospace}\n'
            '.kpi-card{transition:.2s}.kpi-card:hover{transform:translateY(-2px);'
            'box-shadow:0 4px 12px rgba(0,0,0,.1)}\n'
            '::-webkit-scrollbar-thumb{background:#9ca3af;border-radius:3px}\n'
            'table{width:100%;border-collapse:collapse}\n'
            'thead th{position:sticky;top:0;z-index:10;'
            'background:#3C3489;color:white;'
            'padding:10px 12px;text-align:left;'
            'font-size:11px;font-weight:700;'
            'letter-spacing:.05em;text-transform:uppercase}\n'
            '.dark thead th{background:#1e1a4a}\n'
            'tbody tr{border-bottom:1px solid #f3f4f6}\n'
            '.dark tbody tr{border-bottom:1px solid #374151}\n'
            'tbody tr:nth-child(even){background:#fafafa}\n'
            '.dark tbody tr:nth-child(even){background:#1f2937}\n'
            'tbody tr:hover{background:#EEF2FF}\n'
            'tbody td{padding:7px 12px;font-size:12px}\n'
            '.neon-glow{'
            'filter:drop-shadow(0 0 6px currentColor)'
            ' drop-shadow(0 0 12px currentColor)'
            ' drop-shadow(0 0 20px currentColor);'
            'transition:filter .15s ease;}\n'
            '.ftth-popup .leaflet-popup-content-wrapper{'
            '  padding:0;border-radius:10px;overflow:hidden;'
            '  box-shadow:0 8px 30px rgba(0,0,0,.22);min-width:260px;}\n'
            '.ftth-popup .leaflet-popup-content{margin:0;width:auto!important}\n'
            '.ftth-popup-inner{font-family:"Segoe UI",sans-serif;min-width:250px;max-width:340px}\n'
            '.popup-header{display:flex;flex-direction:column;padding:10px 14px;gap:2px}\n'
            '.popup-layer-name{font-size:11px;font-weight:800;color:rgba(255,255,255,.85);'
            'letter-spacing:.08em;text-transform:uppercase}\n'
            '.popup-main-val{font-size:14px;font-weight:700;color:#fff;'
            'word-break:break-all}\n'
            '.popup-status{padding:6px 14px 4px;background:#f9fafb;'
            'border-bottom:1px solid #e5e7eb}\n'
            '.ftth-badge{display:inline-block;padding:2px 10px;border-radius:20px;'
            'font-size:10px;font-weight:700;letter-spacing:.04em}\n'
            '.badge-ok{background:#dcfce7;color:#166534}\n'
            '.badge-err{background:#fee2e2;color:#991b1b;'
            'box-shadow:0 0 8px rgba(239,68,68,.4)}\n'
            '.badge-conf{background:#e0f2fe;color:#075985}\n'
            '.popup-table-wrap{max-height:260px;overflow-y:auto;padding:4px 0 8px}\n'
            '.popup-table{width:100%;border-collapse:collapse;font-size:11px}\n'
            '.popup-key{padding:3px 14px;font-weight:600;color:#6b7280;'
            'white-space:nowrap;vertical-align:top;width:40%}\n'
            '.popup-val{padding:3px 14px;color:#111827;word-break:break-word}\n'
            '.popup-table tr:nth-child(even){background:#f9fafb}\n'
            '.popup-table tr:hover{background:#eff6ff}\n'
            '.map-filter{transition:all .18s;cursor:pointer;font-size:11px;'
            'padding:4px 14px;border-radius:20px;font-weight:600}\n'
            '.map-filter:hover{opacity:.85}\n'
            '</style>\n'
            '</head>\n'
            '<body class="bg-gray-50 dark:bg-gray-900 text-gray-800 '
            'dark:text-gray-100 transition-colors duration-300">\n'

            '<header class="bg-gradient-to-r from-indigo-900 via-indigo-700 '
            'to-blue-800 text-white px-6 py-3 flex '
            'items-center justify-between gap-4 shadow-xl">\n'
            '<div class="flex items-center min-w-[150px]">' +
            amaris_img + '</div>\n'
            '<div class="flex-1 text-center">\n'
            '<h1 class="text-lg font-bold">Rapport FTTH Mayotte - ' +
            project_name + '</h1>\n'
            '<p class="text-xs opacity-80 mt-0.5">' +
            date_now + ' | ZSRO : ' + zsro_label +
            ' | NRO : ' + nro_label +
            ' | Phase : ' + phase + '</p>\n'
            '</div>\n'
            '<div class="flex items-center gap-3 min-w-[150px] justify-end">\n' +
            orange_img +
            '\n<button onclick="toggleDark()" '
            'class="p-2 rounded-full bg-white/10 hover:bg-white/20 '
'transition text-lg" id="themeBtn">&#127769;</button>\n'
            '</div>\n'
            '</header>\n'

            '<nav class="bg-indigo-800 dark:bg-indigo-900 flex gap-1 px-6 '
            'overflow-x-auto border-b border-white/10">\n'
            '<button class="nav-btn active text-sm font-medium px-4 py-2.5 text-white" '
            'onclick="showPage(\'dashboard\',this)">Dashboard</button>\n'
            '<button class="nav-btn text-sm font-medium px-4 py-2.5 text-white" '
            'onclick="showPage(\'map\',this)">Carte</button>\n'
            '<button class="nav-btn text-sm font-medium px-4 py-2.5 text-white" '
            'onclick="showPage(\'context\',this)">Contexte ZSRO</button>\n'
            '<button class="nav-btn text-sm font-medium px-4 py-2.5 text-white" '
            'onclick="showPage(\'table\',this)">Tableau (' +
            str(total_err) + ')</button>\n'
            '<button class="nav-btn text-sm font-medium px-4 py-2.5 text-white" '
            'onclick="showPage(\'budget\',this)">Budget</button>\n'
            '</nav>\n'

            '<!-- DASHBOARD -->\n'
            '<div class="page active p-6" id="page-dashboard">\n'
            '<div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-5">\n'
            '<div class="kpi-card bg-white dark:bg-gray-800 rounded-xl p-4 '
            'text-center border shadow-sm">'
            '<div class="text-3xl font-bold text-red-600">' +
            str(total_err) + '</div>'
            '<div class="text-xs text-gray-500 mt-1 uppercase">Erreurs</div></div>\n'
            '<div class="kpi-card bg-white dark:bg-gray-800 rounded-xl p-4 '
            'text-center border shadow-sm">'
            '<div class="text-3xl font-bold text-green-700">' +
            str(corrected) + '</div>'
            '<div class="text-xs text-gray-500 mt-1 uppercase">Corrigees</div></div>\n'
            '<div class="kpi-card bg-white dark:bg-gray-800 rounded-xl p-4 '
            'text-center border shadow-sm">'
            '<div class="text-3xl font-bold text-orange-500">' +
            str(total_err - corrected) + '</div>'
            '<div class="text-xs text-gray-500 mt-1 uppercase">Restantes</div></div>\n'
            '<div class="kpi-card bg-white dark:bg-gray-800 rounded-xl p-4 '
            'text-center border shadow-sm">'
            '<div class="text-3xl font-bold text-blue-700">' +
            str(len(stats_couche)) + '</div>'
            '<div class="text-xs text-gray-500 mt-1 uppercase">Couches</div></div>\n'
            '<div class="kpi-card bg-white dark:bg-gray-800 rounded-xl p-4 '
            'text-center border shadow-sm">'
            '<div class="text-3xl font-bold text-indigo-600">' +
            str(sum(total_entites.values())) + '</div>'
            '<div class="text-xs text-gray-500 mt-1 uppercase">Entites</div></div>\n'
            '</div>\n'

            '<div class="bg-white dark:bg-gray-800 rounded-xl p-5 mb-5 border shadow-sm">\n'
            '<div class="flex justify-between items-center mb-2">'
            '<span class="text-sm font-semibold">Avancement correction</span>'
            '<span class="text-2xl font-bold text-green-700">' +
            str(pct_correction) + '%</span></div>\n'
            '<div class="gauge-bar">'
            '<div class="gauge-fill" style="width:' +
            str(pct_correction) + '%"></div></div>\n'
            '<div class="flex justify-between text-xs text-gray-400 mt-1">'
            '<span>0%</span><span>' + str(corrected) + '/' +
            str(total_err) + ' corrigees</span><span>100%</span></div>\n'
            '</div>\n'

            '<div class="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-5">\n'
            '<div class="lg:col-span-2 bg-white dark:bg-gray-800 rounded-xl p-5 border shadow-sm">'
            '<h3 class="text-xs font-bold uppercase tracking-wider text-indigo-600 mb-4">'
            'Erreurs par couche</h3>'
            '<canvas id="chartCouche" height="100"></canvas></div>\n'
            '<div class="bg-white dark:bg-gray-800 rounded-xl p-5 border shadow-sm">'
            '<h3 class="text-xs font-bold uppercase tracking-wider text-indigo-600 mb-4">'
            'Repartition</h3>'
            '<canvas id="chartPie" height="160"></canvas></div>\n'
            '</div>\n'
            '<div class="bg-white dark:bg-gray-800 rounded-xl p-5 border shadow-sm">'
            '<h3 class="text-xs font-bold uppercase tracking-wider text-indigo-600 mb-4">'
            'Erreurs par categorie</h3>'
            '<canvas id="chartSection" height="60"></canvas></div>\n'
            '</div>\n'

            # ── Page Carte ───────────────────────────────────────
            '<!-- CARTE -->\n'
            '<div class="map-page" id="page-map">\n'
            '  <div id="map"></div>\n'
            '  <div class="w-96 flex flex-col bg-white dark:bg-gray-800'
            ' border-l border-gray-200 dark:border-gray-700 shadow-xl">\n'
            '    <div class="bg-indigo-700 text-white px-4 py-3'
            ' font-semibold text-sm flex justify-between items-center">\n'
            '      <span>&#128506; Couches du projet</span>\n'
            '      <span class="bg-white/20 rounded-full px-2 py-0.5'
            ' text-xs" id="errCount">' + str(total_err) + '</span>\n'
            '    </div>\n'
            # Filtres
            '    <div class="flex gap-1 p-2 border-b border-gray-100'
            ' dark:border-gray-700 flex-wrap">\n'
            '      <button onclick="setMapFilter(\'all\',this)"'
            ' class="map-filter active text-xs px-2 py-1 rounded-full'
            ' bg-indigo-600 text-white font-medium">Tout</button>\n'
            '      <button onclick="setMapFilter(\'errors\',this)"'
            ' class="map-filter text-xs px-2 py-1 rounded-full border'
            ' border-gray-300 font-medium">&#10007; Erreurs</button>\n'
            '      <button onclick="setMapFilter(\'corrected\',this)"'
            ' class="map-filter text-xs px-2 py-1 rounded-full border'
            ' border-gray-300 font-medium">&#10003; Corriges</button>\n'
            '      <button onclick="setMapFilter(\'ok\',this)"'
            ' class="map-filter text-xs px-2 py-1 rounded-full border'
            ' border-gray-300 font-medium">&#10004; Conformes</button>\n'
            '    </div>\n'
            # Toggles couches
            '    <div class="p-2 border-b border-gray-100 dark:border-gray-700">\n'
            '      <div class="text-xs font-semibold text-gray-500 uppercase mb-1">Couches</div>\n'
            '      <div class="flex flex-wrap gap-1" id="layerToggles"></div>\n'
            '    </div>\n'
            # Liste features
            '    <div class="flex-1 overflow-y-auto text-xs" id="featList"'
            ' style="max-height:calc(100vh - 320px)"></div>\n'
            # Fonds
            '    <div class="p-2 border-t border-gray-100 dark:border-gray-700">\n'
            '      <div class="flex gap-1 flex-wrap">\n'
            '        <button id="btn-osm" onclick="setBasemap(\'osm\')"'
            ' class="tile-btn text-xs px-2 py-1 rounded-full'
            ' bg-indigo-600 text-white font-medium">OSM</button>\n'
            '        <button id="btn-sat" onclick="setBasemap(\'sat\')"'
            ' class="tile-btn text-xs px-2 py-1 rounded-full border'
            ' border-gray-300 font-medium">Satellite</button>\n'
            '        <button id="btn-topo" onclick="setBasemap(\'topo\')"'
            ' class="tile-btn text-xs px-2 py-1 rounded-full border'
            ' border-gray-300 font-medium">Relief</button>\n'
            '      </div>\n'
            '    </div>\n'
            '  </div>\n'
            '</div>\n'

            '<!-- CONTEXTE ZSRO -->\n'
            '<div class="page p-6" id="page-context">\n'
            '<div class="bg-gradient-to-r from-indigo-700 to-blue-700 '
            'text-white rounded-xl p-6 mb-6">\n'
            '<h2 class="text-xl font-bold mb-1">Contexte ZSRO - ' +
            zsro.get('code', 'N/A') + '</h2>\n'
            '<p class="text-sm opacity-90">'
            'PM Ref : ' + zsro.get('refpm', 'N/A') +
            ' | NRO : ' + nro_names +
            ' | Commune : ' + commune_pm + '</p>\n'
            '</div>\n'

            '<div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">\n'
            '<div class="kpi-card bg-white dark:bg-gray-800 rounded-xl p-4 '
            'text-center border shadow-sm">'
            '<div class="text-2xl font-bold text-indigo-600">' +
            str(zsro.get('pcn_ftth', 0)) + '</div>'
            '<div class="text-xs text-gray-500 mt-1 uppercase">Logements FTTH</div></div>\n'
            '<div class="kpi-card bg-white dark:bg-gray-800 rounded-xl p-4 '
            'text-center border shadow-sm">'
            '<div class="text-2xl font-bold text-blue-600">' +
            str(zsro.get('pcn_ftte', 0)) + '</div>'
            '<div class="text-xs text-gray-500 mt-1 uppercase">Logements FTTE</div></div>\n'
            '<div class="kpi-card bg-white dark:bg-gray-800 rounded-xl p-4 '
            'text-center border shadow-sm">'
            '<div class="text-2xl font-bold text-green-600">' +
            str(nb_zpa) + '</div>'
            '<div class="text-xs text-gray-500 mt-1 uppercase">Zones ZPA</div></div>\n'
            '<div class="kpi-card bg-white dark:bg-gray-800 rounded-xl p-4 '
            'text-center border shadow-sm">'
            '<div class="text-2xl font-bold text-orange-500">' +
            str(nb_zpbo) + '</div>'
            '<div class="text-xs text-gray-500 mt-1 uppercase">Zones ZPBO</div></div>\n'
            '<div class="kpi-card bg-white dark:bg-gray-800 rounded-xl p-4 '
            'text-center border shadow-sm">'
            '<div class="text-2xl font-bold text-purple-600">' +
            str(nb_adresses) + '</div>'
            '<div class="text-xs text-gray-500 mt-1 uppercase">Adresses</div></div>\n'
            '</div>\n'

            '<div class="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-6">\n'
            '<div class="bg-white dark:bg-gray-800 rounded-xl p-5 border shadow-sm">'
            '<h3 class="text-xs font-bold uppercase tracking-wider '
            'text-indigo-600 mb-4">Etat logements (LEG/ILL/N)</h3>'
            '<canvas id="chartAdComment" height="200"></canvas></div>\n'
            '<div class="bg-white dark:bg-gray-800 rounded-xl p-5 border shadow-sm">'
            '<h3 class="text-xs font-bold uppercase tracking-wider '
            'text-indigo-600 mb-4">Immeubles vs Pavillons</h3>'
            '<canvas id="chartImb" height="200"></canvas></div>\n'
            '<div class="bg-white dark:bg-gray-800 rounded-xl p-5 border shadow-sm">'
            '<h3 class="text-xs font-bold uppercase tracking-wider '
            'text-indigo-600 mb-4">FTTH Particuliers vs Pro</h3>'
            '<canvas id="chartLogPro" height="200"></canvas></div>\n'
            '</div>\n'

            '  <div class="bg-white dark:bg-gray-800 rounded-xl p-5'
            ' border shadow-sm mb-6">\n'
            '    <h3 class="text-xs font-bold uppercase tracking-wider'
            ' text-indigo-600 mb-4">Batiments et prises par ZPA'
            ' (echelle log)</h3>\n'
            '    <div style="position:relative;height:240px">\n'
            '      <canvas id="chartBatZpa"></canvas>\n'
            '    </div>\n'
            '  </div>\n'

            '<div class="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-6">\n'
            '<div class="bg-white dark:bg-gray-800 rounded-xl p-5 border shadow-sm">'
            '<h3 class="text-xs font-bold uppercase tracking-wider '
            'text-indigo-600 mb-4">État des supports</h3>'
            '<canvas id="chartSupProptyp" height="200"></canvas></div>\n'
            '<div class="bg-white dark:bg-gray-800 rounded-xl p-5 border shadow-sm">'
            '<h3 class="text-xs font-bold uppercase tracking-wider '
            'text-indigo-600 mb-4">Propriété des supports</h3>'
            '<canvas id="chartSupProp" height="200"></canvas></div>\n'
            '<div class="bg-white dark:bg-gray-800 rounded-xl p-5 border shadow-sm">'
            '<h3 class="text-xs font-bold uppercase tracking-wider '
            'text-indigo-600 mb-4">Types de PB</h3>'
            '<canvas id="chartPbTypes" height="200"></canvas></div>\n'
            '</div>\n' +

            # Section socio-économique Mayotte
            '<div class="mt-6 bg-white dark:bg-gray-800 rounded-xl'
            ' border border-gray-200 shadow-sm overflow-hidden">'
            '<div class="bg-gradient-to-r from-indigo-800 to-blue-700 px-5 py-3 text-white">'
            '<h3 class="font-bold text-sm">&#127758; Contexte socio-\u00e9conomique \u2014 Mayotte</h3>'
            '<p class="text-xs opacity-80 mt-0.5">Sources : INSEE 2024 \u00b7 IEDOM \u00b7 AFD \u00b7 ARCEP</p>'
            '</div>'
            '<div class="p-5">'
            '<div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">'
            '<div class="bg-indigo-50 rounded-lg p-3 text-center border border-indigo-100">'
            '<div class="text-2xl font-bold text-indigo-700">321\u202f000</div>'
            '<div class="text-xs text-gray-500 mt-1 uppercase">Habitants (2021)</div></div>'
            '<div class="bg-blue-50 rounded-lg p-3 text-center border border-blue-100">'
            '<div class="text-2xl font-bold text-blue-700">857/km\u00b2</div>'
            '<div class="text-xs text-gray-500 mt-1 uppercase">Densit\u00e9 pop.</div></div>'
            '<div class="bg-green-50 rounded-lg p-3 text-center border border-green-100">'
            '<div class="text-2xl font-bold text-green-700">3\u202f230\u202f\u20ac</div>'
            '<div class="text-xs text-gray-500 mt-1 uppercase">PIB/habitant</div></div>'
            '<div class="bg-orange-50 rounded-lg p-3 text-center border border-orange-100">'
            '<div class="text-2xl font-bold text-orange-600">35\u202f%</div>'
            '<div class="text-xs text-gray-500 mt-1 uppercase">Taux ch\u00f4mage</div></div>'
            '</div>'
            '<div class="overflow-x-auto mb-4">'
            '<table class="text-xs w-full border border-gray-200 rounded-lg overflow-hidden">'
            '<thead><tr class="bg-indigo-700 text-white">'
            '<th class="p-2 text-left">Indicateur</th>'
            '<th class="p-2 text-center">Valeur</th>'
            '<th class="p-2 text-center">Contexte</th>'
            '</tr></thead><tbody>'
            '<tr><td class="p-2 font-medium">Croissance d\u00e9mo.</td>'
            '<td class="p-2 text-center font-bold text-indigo-600">+3,8\u202f%/an</td>'
            '<td class="p-2 text-gray-500">Plus forte de France (INSEE 2021)</td></tr>'
            '<tr class="bg-gray-50"><td class="p-2 font-medium">M\u00e9nages sans internet</td>'
            '<td class="p-2 text-center font-bold text-red-600">~62\u202f%</td>'
            '<td class="p-2 text-gray-500">Fracture num\u00e9rique (ARCEP 2022)</td></tr>'
            '<tr><td class="p-2 font-medium">PIB total (2021)</td>'
            '<td class="p-2 text-center font-bold text-green-700">1,04 Md\u202f\u20ac</td>'
            '<td class="p-2 text-gray-500">+4,5\u202f%/an (IEDOM)</td></tr>'
            '<tr class="bg-gray-50"><td class="p-2 font-medium">Population &lt;15 ans</td>'
            '<td class="p-2 text-center font-bold text-purple-600">47\u202f%</td>'
            '<td class="p-2 text-gray-500">Pop. tr\u00e8s jeune, besoin num. fort</td></tr>'
            '<tr><td class="p-2 font-medium">Abonn. haut d\u00e9bit</td>'
            '<td class="p-2 text-center font-bold text-teal-600">~42\u202f000</td>'
            '<td class="p-2 text-gray-500">Principalement 4G fixe (ARCEP 2023)</td></tr>'
            '</tbody></table></div>'
            '<div class="bg-indigo-50 border border-indigo-200 rounded-lg p-4 text-xs text-indigo-900">'
            '<p class="font-bold mb-2">&#9888;&#65039; Enjeux du d\u00e9ploiement FTTH \u00e0 Mayotte</p>'
            '<ul style="padding-left:1.2em;list-style:disc;line-height:1.9">'
            '<li>R\u00e9duire la <b>fracture num\u00e9rique</b> dans un territoire \u00e0 forte croissance</li>'
            '<li>Soutenir le <b>d\u00e9veloppement \u00e9conomique</b> local</li>'
            '<li>Am\u00e9liorer l\'acc\u00e8s aux <b>services publics d\u00e9mat\u00e9rialis\u00e9s</b></li>'
            '<li>R\u00e9pondre au <b>Plan France Tr\u00e8s Haut D\u00e9bit</b></li>'
            '<li>Cr\u00e9er des <b>emplois locaux</b> li\u00e9s au r\u00e9seau</li>'
            '</ul></div>'
            '</div></div>\n'
            +
            ('<div class="bg-gray-50 dark:bg-gray-700 rounded-xl p-4 '
             'border"><div class="text-xs font-semibold text-gray-500 '
             'uppercase mb-2">Commentaire ZSRO</div>'
             '<p class="text-sm text-gray-700 dark:text-gray-300">' +
             zsro_comment + '</p></div>\n'
             if zsro_comment else '') +

            '</div>\n'

            '<!-- TABLEAU -->\n'
            '<div class="page p-6" id="page-table">\n'
            '<div class="flex gap-2 flex-wrap mb-4 items-center">'
            '<span class="text-xs font-semibold text-gray-500 uppercase">'
            'Filtrer :</span>'
            '<button onclick="filterSec(\'all\',this)" '
            'class="filter-btn active text-xs px-3 py-1.5 rounded-full '
            'border font-medium">Tout</button>' +
            sec_btns + '</div>\n'
            '<div class="overflow-auto rounded-xl border shadow-sm" '
            'style="max-height:calc(100vh - 260px)">'
            '<table><thead><tr>'
            '<th>CORRECTION</th><th>CODE</th>'
            '<th>COUCHE</th><th>LIBELLE</th><th>INFO</th>'
            '</tr></thead>'
            '<tbody id="errTableBody">' + rows_html + '</tbody>'
            '</table></div>\n'
            '</div>\n'

            # ── Page Budget ──────────────────────────────────────
            '<div class="page p-6 overflow-y-auto" id="page-budget">\n'
            '  <div class="bg-gradient-to-r from-green-700 to-teal-600'
            ' text-white rounded-xl p-5 mb-5">\n'
            '    <h2 class="text-lg font-bold mb-1">&#128181;'
            ' Estimation budg\u00e9taire FTTH &mdash; ' + zsro_label + '</h2>\n'
            '    <p class="text-xs opacity-80">Couts moyens indicatifs.'
            ' Fourchette basse/haute affichée. Moyenne utilisée'
            ' pour le total.</p>\n'
            '  </div>\n'
            '  <div id="budgetContent"></div>\n'
            '</div>\n'

            '<script>\n'
            'const adComment=' + ad_comment_j + ';\n'
            'const adImb=' + ad_imb_j + ';\n'
            'const adLogPro=' + ad_logpro_j + ';\n'
            'const nbBatZpa=' + nb_bat_zpa_j + ';\n'
            'const nbPrisesZpa=' + nb_prises_zpa_j + ';\n'
            'const supProptyp=' + sup_proptyp_j + ';\n'
            'const supProp=' + sup_prop_j + ';\n'
            'const pbTypes=' + pb_types_j + ';\n'
            'let contextChartsBuilt=false;\n'
            'function initContextCharts(){\n'
            '  if(contextChartsBuilt)return;\n'
            '  contextChartsBuilt=true;\n'
            '  const adCommentColors={'
            '"LEG":"#22c55e","ILL":"#ef4444","N":"#94a3b8","N/A":"#cbd5e1"};\n'
            '  mkChart("chartAdComment","doughnut",'
            'Object.keys(adComment),Object.values(adComment),'
            'Object.keys(adComment).map(k=>adCommentColors[k]||"#94a3b8"));\n'
            '  mkChart("chartImb","doughnut",'
            '["Immeubles (OUI)","Pavillons (NON)"],'
            '[adImb["OUI"]||0,adImb["NON"]||0],'
            '["#3C3489","#60a5fa"]);\n'
            '  mkChart("chartLogPro","doughnut",'
            '["Particuliers (pcn_log)","Pro (pcn_pro)"],'
            '[adLogPro["log"]||0,adLogPro["pro"]||0],'
            '["#2E7D32","#f59e0b"]);\n'
            'setTimeout(function buildBatZpaChart(){\n'
            '  const el=document.getElementById("chartBatZpa");\n'
            '  if(!el){setTimeout(buildBatZpaChart,300);return;}\n'
            '  const keys=Object.keys(nbBatZpa);\n'
            '  if(!keys.length){\n'
            '    const p=el.parentElement;\n'
            '    if(p)p.innerHTML="<p style=\'text-align:center;color:#9ca3af;font-size:12px;padding:20px\'>Aucune donn\u00e9e ZPA disponible</p>";\n'
            '    return;\n'
            '  }\n'
            '  el.style.display="block";\n'
            '  el.style.height="220px";el.style.width="100%";\n'
            '  const batVals=keys.map(k=>Math.max(nbBatZpa[k]||0,0.5));\n'
            '  const priVals=keys.map(k=>Math.max(nbPrisesZpa[k]||0,0.5));\n'
            '  new Chart(el,{\n'
            '    type:"bar",\n'
            '    data:{labels:keys,datasets:[\n'
            '      {label:"B\u00e2timents (adresses)",data:batVals,\n'
            '       backgroundColor:"rgba(60,52,137,0.82)",borderColor:"#3C3489",borderWidth:1,borderRadius:4},\n'
            '      {label:"Prises FTTH (pcn_ftth)",data:priVals,\n'
            '       backgroundColor:"rgba(230,81,0,0.78)",borderColor:"#E65100",borderWidth:1,borderRadius:4}\n'
            '    ]},\n'
            '    options:{responsive:true,maintainAspectRatio:false,\n'
            '      plugins:{\n'
            '        legend:{display:true,position:"bottom",labels:{font:{size:10},boxWidth:12,padding:8}},\n'
            '        tooltip:{callbacks:{label:ctx=>" "+ctx.dataset.label+" : "+Math.round(ctx.raw)}}\n'
            '      },\n'
            '      scales:{\n'
            '        y:{type:"logarithmic",min:0.5,\n'
            '          ticks:{callback:function(v){\n'
            '            const nv=[1,2,5,10,20,50,100,200,500,1000,2000];\n'
            '            return nv.some(n=>Math.abs(v-n)<0.01)?Math.round(v):"";\n'
            '          },maxTicksLimit:8},\n'
            '          title:{display:true,text:"Nb (\u00e9chelle log)",font:{size:9}}},\n'
            '        x:{ticks:{maxRotation:55,minRotation:30,font:{size:8}}}\n'
            '      }\n'
            '    }\n'
            '  });\n'
            '},150);\n'
            '  mkChart("chartSupProptyp","doughnut",'
            'Object.keys(supProptyp),Object.values(supProptyp),'
            '["#ef4444","#22c55e","#f59e0b","#94a3b8"]);\n'
            '  mkChart("chartSupProp","doughnut",'
            'Object.keys(supProp),Object.values(supProp),COLORS);\n'
            '  mkChart("chartPbTypes","doughnut",'
            'Object.keys(pbTypes),Object.values(pbTypes),'
            '["#3C3489","#1565C0","#E65100","#2E7D32","#94a3b8"]);\n'
            '}\n'
            'document.addEventListener("DOMContentLoaded",function(){\n'
            '  Chart.defaults.font.family="\'Segoe UI\',sans-serif";\n'
            '  Chart.defaults.font.size=12;\n'
            '  new Chart(document.getElementById("chartCouche"),{type:"bar",'
            'data:{labels:' + layers_labels + ','
            'datasets:[{label:"Erreurs",data:' + layers_values + ','
            'backgroundColor:COLORS,borderRadius:6}]},'
            'options:{responsive:true,indexAxis:"y",'
            'plugins:{legend:{display:false}},'
            'scales:{x:{beginAtZero:true,ticks:{stepSize:1}}}}});\n'
            '  new Chart(document.getElementById("chartPie"),{type:"doughnut",'
            'data:{labels:' + section_labels + ','
            'datasets:[{data:' + section_values + ','
            'backgroundColor:COLORS,borderWidth:2,hoverOffset:8}]},'
            'options:{responsive:true,'
            'plugins:{legend:{position:"bottom",'
            'labels:{font:{size:10},boxWidth:12}}}}});\n'
            '  new Chart(document.getElementById("chartSection"),{type:"bar",'
            'data:{labels:' + section_labels + ','
            'datasets:[{label:"Erreurs",data:' + section_values + ','
            'backgroundColor:COLORS,borderRadius:6}]},'
            'options:{responsive:true,'
            'plugins:{legend:{display:false}},'
            'scales:{y:{beginAtZero:true,ticks:{stepSize:1}}}}});\n'
            '});\n'
            '</script>\n'
            '</body>\n'
            '</html>\n'
        )
        return html

    def _on_close(self):
        self.auto_check_timer.stop()
        self.close()