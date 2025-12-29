import sys
import os
import json
import random
from pathlib import Path

from PySide6 import QtCore as qtc
from PySide6 import QtGui as qtg
from PySide6 import QtWidgets as qtw

# =============================================================================
# 1. HELPER CLASSES & UTILS
# =============================================================================

def apply_dark_theme(app):
    app.setStyle("Fusion")
    palette = qtg.QPalette()
    palette.setColor(qtg.QPalette.Window, qtg.QColor(53, 53, 53))
    palette.setColor(qtg.QPalette.WindowText, qtg.Qt.white)
    palette.setColor(qtg.QPalette.Base, qtg.QColor(25, 25, 25))
    palette.setColor(qtg.QPalette.AlternateBase, qtg.QColor(53, 53, 53))
    palette.setColor(qtg.QPalette.ToolTipBase, qtg.Qt.white)
    palette.setColor(qtg.QPalette.ToolTipText, qtg.Qt.white)
    palette.setColor(qtg.QPalette.Text, qtg.Qt.white)
    palette.setColor(qtg.QPalette.Button, qtg.QColor(53, 53, 53))
    palette.setColor(qtg.QPalette.ButtonText, qtg.Qt.white)
    palette.setColor(qtg.QPalette.BrightText, qtg.Qt.red)
    palette.setColor(qtg.QPalette.Link, qtg.QColor(42, 130, 218))
    palette.setColor(qtg.QPalette.Highlight, qtg.QColor(42, 130, 218))
    palette.setColor(qtg.QPalette.HighlightedText, qtg.Qt.black)
    app.setPalette(palette)

def get_color_for_id(track_id):
    if track_id is None or track_id <= 0:
        return qtg.QColor(200, 200, 200)
    
    random.seed(track_id)
    # Range 100-255 ensures brighter, more vivid colors
    return qtg.QColor(
        random.randint(100, 255), 
        random.randint(100, 255), 
        random.randint(100, 255)
    )

class CreateObjectDialog(qtw.QDialog):
    """Dialog to prompt user for Class and Track ID before drawing."""
    def __init__(self, parent=None, classes=None, next_track_id=1):
        super().__init__(parent)
        self.setWindowTitle("New Object Details")
        self.classes = classes or {} 
        
        layout = qtw.QVBoxLayout(self)
        
        layout.addWidget(qtw.QLabel("Select Class:"))
        self.combo_classes = qtw.QComboBox()
        for name, cid in self.classes.items():
            self.combo_classes.addItem(f"{name} ({cid})", cid)
        layout.addWidget(self.combo_classes)
        
        layout.addWidget(qtw.QLabel("Track ID:"))
        self.spin_track = qtw.QSpinBox()
        self.spin_track.setRange(1, 99999)
        self.spin_track.setValue(next_track_id)
        layout.addWidget(self.spin_track)
        
        btns = qtw.QDialogButtonBox(qtw.QDialogButtonBox.Ok | qtw.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self):
        cid = self.combo_classes.currentData()
        tid = self.spin_track.value()
        class_name = self.combo_classes.currentText().split(' (')[0]
        return cid, tid, class_name

# =============================================================================
# 2. DATA MANAGER
# =============================================================================
class AnnotationManager:
    def __init__(self):
        self.boxes = {} 
        self.next_id = 0
        self.next_suggestion_track_id = 1
        self.current_json_path = ""
        # Store all unique tracks found in the folder: {track_id: class_id}
        self.folder_unique_tracks = {} 

    def scan_folder(self, json_folder):
        """Scans all JSON files to build a list of all existing objects."""
        self.folder_unique_tracks = {}
        self.next_suggestion_track_id = 1
        
        if not os.path.exists(json_folder): return

        for filename in os.listdir(json_folder):
            if filename.endswith(".json") and not filename.startswith("classes"):
                try:
                    with open(os.path.join(json_folder, filename), 'r') as f:
                        data = json.load(f)
                        for entry in data.values():
                            if 'track_id' in entry and 'class' in entry:
                                tid = entry['track_id']
                                cid = entry['class']
                                if tid > 0:
                                    self.folder_unique_tracks[tid] = cid
                                    if tid >= self.next_suggestion_track_id:
                                        self.next_suggestion_track_id = tid + 1
                except: continue

    def load_from_file(self, filepath):
        self.boxes = {}
        self.current_json_path = filepath
        self.next_id = 0 
        
        if not os.path.exists(filepath):
            return

        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                
            for key, entry in data.items():
                if 'box' not in entry: continue
                box_id = int(key)
                self.boxes[box_id] = entry
                if box_id >= self.next_id: self.next_id = box_id + 1
                
        except json.JSONDecodeError:
            print(f"Error reading JSON: {filepath}")

    def save_to_file(self):
        if not self.current_json_path: return
        save_data = {bid: data for bid, data in self.boxes.items() if data.get('class', -1) != -1}
        with open(self.current_json_path, 'w') as f:
            json.dump(save_data, f, indent=4)
            
    def add_box(self, rect, class_id, track_id):
        box_id = self.next_id
        self.next_id += 1
        self.boxes[box_id] = {
            'box': [rect.left(), rect.top(), rect.right(), rect.bottom()],
            'class': class_id,
            'track_id': track_id
        }
        
        # Update global list dynamically
        if track_id > 0:
            self.folder_unique_tracks[track_id] = class_id
            if track_id >= self.next_suggestion_track_id:
                self.next_suggestion_track_id = track_id + 1
                
        return box_id

    def update_box(self, box_id, rect=None):
        if box_id in self.boxes and rect:
            self.boxes[box_id]['box'] = [rect.left(), rect.top(), rect.right(), rect.bottom()]
    
    def delete_box(self, box_id):
        if box_id in self.boxes: del self.boxes[box_id]

        
    def interpolate_track(self, target_track_id, json_folder, image_files):
        """
        Locates all instances of target_track_id across all files.
        Linearly interpolates boxes between existing keyframes.
        """
        # 1. Gather all existing keyframes for this track
        # keyframes = { frame_index: { 'box': [x1,y1,x2,y2], 'class': class_id } }
        keyframes = {}
        
        # Iterate through the correctly sorted image files list
        for idx, image_filename in enumerate(image_files):
            # Construct expected JSON path for this image
            json_filename = os.path.splitext(image_filename)[0] + ".json"
            json_path = os.path.join(json_folder, json_filename)
            
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r') as f:
                        data = json.load(f)
                        # Check if our target track is in this file
                        for entry in data.values():
                            if entry.get('track_id') == target_track_id:
                                keyframes[idx] = {
                                    'box': entry['box'],
                                    'class': entry['class']
                                }
                                break
                except: pass

        # 2. Sort keyframes by frame index (Logic from here is standard)
        sorted_indices = sorted(keyframes.keys())
        if len(sorted_indices) < 2:
            return 0 # Not enough points to interpolate

        count = 0
        
        # 3. Iterate through pairs (Frame A -> Frame B)
        for i in range(len(sorted_indices) - 1):
            start_idx = sorted_indices[i]
            end_idx = sorted_indices[i+1]
            
            # If frames are adjacent, nothing to fill
            steps = end_idx - start_idx
            if steps <= 1: continue

            start_data = keyframes[start_idx]
            end_data = keyframes[end_idx]
            
            # Calculate step size per frame
            sx1, sy1, sx2, sy2 = start_data['box']
            ex1, ey1, ex2, ey2 = end_data['box']
            
            dx1 = (ex1 - sx1) / steps
            dy1 = (ey1 - sy1) / steps
            dx2 = (ex2 - sx2) / steps
            dy2 = (ey2 - sy2) / steps
            
            # 4. Fill the gap
            class_id = start_data['class']
            
            for step in range(1, steps):
                target_idx = start_idx + step
                
                # Calculate new coords
                nx1 = sx1 + (dx1 * step)
                ny1 = sy1 + (dy1 * step)
                nx2 = sx2 + (dx2 * step)
                ny2 = sy2 + (dy2 * step)
                
                # Load Target JSON
                target_filename = image_files[target_idx]
                target_path = os.path.join(json_folder, os.path.splitext(target_filename)[0] + ".json")
                
                file_data = {}
                if os.path.exists(target_path):
                    with open(target_path, 'r') as f:
                        file_data = json.load(f)
                
                # Safety Check: Don't overwrite if track already exists there
                exists = False
                for v in file_data.values():
                    if v.get('track_id') == target_track_id:
                        exists = True
                        break
                if exists: continue

                # Add new box
                new_bid = 0
                if file_data:
                    try:
                        new_bid = max([int(k) for k in file_data.keys()]) + 1
                    except: new_bid = 0
                
                file_data[str(new_bid)] = {
                    'box': [nx1, ny1, nx2, ny2],
                    'class': class_id,
                    'track_id': target_track_id
                }
                
                with open(target_path, 'w') as f:
                    json.dump(file_data, f, indent=4)
                count += 1
                
        return count

# =============================================================================
# 3. VISUAL ITEMS
# =============================================================================

class BoxItem(qtw.QGraphicsRectItem):
    def __init__(self, rect, box_id, track_id, manager, main_window):
        super().__init__(rect)
        self.box_id = box_id
        self.manager = manager
        self.main_window = main_window
        
        self.set_color(track_id)
        
        # Flags
        self.setFlags(
            qtw.QGraphicsItem.ItemIsMovable | 
            qtw.QGraphicsItem.ItemIsSelectable | 
            qtw.QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        
        # Text Label Setup
        self.text = qtw.QGraphicsTextItem(str(track_id), self)
        self.text.setDefaultTextColor(qtg.Qt.white)
        
        # CHANGED: Font size increased from 10 to 14
        self.text.setFont(qtg.QFont("Arial", 14, qtg.QFont.Bold))
        
        # OPTIONAL: Add a black shadow/outline effect to text so it's readable on bright backgrounds
        # This makes the text "pop" regardless of the box color
        shadow = qtw.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(3)
        shadow.setColor(qtg.Qt.black)
        shadow.setOffset(1, 1)
        self.text.setGraphicsEffect(shadow)

        self.update_label_pos()
        
        self.resizing = False
        self.resize_handle = None

    def set_color(self, track_id):
        color = get_color_for_id(track_id)
        
        # CHANGED: Pen width increased from 2 to 4
        self.setPen(qtg.QPen(color, 4))
        
        self.setBrush(qtg.QBrush(qtg.Qt.transparent))

    def update_label_pos(self):
        # Keep text inside top-left corner
        self.text.setPos(self.rect().topLeft())

    def hoverMoveEvent(self, event):
        """Detect which border/corner the mouse is hovering over."""
        pos = event.pos()
        rect = self.rect()
        margin = 10  # Sensitivity area in pixels

        # Coordinates
        left = rect.left()
        right = rect.right()
        top = rect.top()
        bottom = rect.bottom()
        
        # Check regions
        on_left = abs(pos.x() - left) < margin
        on_right = abs(pos.x() - right) < margin
        on_top = abs(pos.y() - top) < margin
        on_bottom = abs(pos.y() - bottom) < margin

        # Determine cursor and handle
        if on_top and on_left:
            self.setCursor(qtg.Qt.SizeFDiagCursor)
            self.resize_handle = "TL"
        elif on_top and on_right:
            self.setCursor(qtg.Qt.SizeBDiagCursor)
            self.resize_handle = "TR"
        elif on_bottom and on_left:
            self.setCursor(qtg.Qt.SizeBDiagCursor)
            self.resize_handle = "BL"
        elif on_bottom and on_right:
            self.setCursor(qtg.Qt.SizeFDiagCursor)
            self.resize_handle = "BR"
        elif on_left:
            self.setCursor(qtg.Qt.SizeHorCursor)
            self.resize_handle = "L"
        elif on_right:
            self.setCursor(qtg.Qt.SizeHorCursor)
            self.resize_handle = "R"
        elif on_top:
            self.setCursor(qtg.Qt.SizeVerCursor)
            self.resize_handle = "T"
        elif on_bottom:
            self.setCursor(qtg.Qt.SizeVerCursor)
            self.resize_handle = "B"
        else:
            self.setCursor(qtg.Qt.ArrowCursor)
            self.resize_handle = None
            
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if self.resize_handle:
            self.resizing = True
            # Prevent moving the box while resizing
            self.setFlag(qtw.QGraphicsItem.ItemIsMovable, False)
        else:
            self.resizing = False
            self.setFlag(qtw.QGraphicsItem.ItemIsMovable, True)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.resizing and self.resize_handle:
            rect = self.rect()
            pos = event.pos()
            
            # Adjust geometry based on active handle
            if "L" in self.resize_handle:
                rect.setLeft(pos.x())
            if "R" in self.resize_handle:
                rect.setRight(pos.x())
            if "T" in self.resize_handle:
                rect.setTop(pos.y())
            if "B" in self.resize_handle:
                rect.setBottom(pos.y())
            
            # Normalize to prevent negative width/height (flipping)
            rect = rect.normalized()

            # Minimum size check (5x5 pixels)
            if rect.width() > 5 and rect.height() > 5:
                self.setRect(rect)
                self.update_label_pos()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.resizing = False
        self.setFlag(qtw.QGraphicsItem.ItemIsMovable, True)
        
        # Save changes
        self.manager.update_box(self.box_id, rect=self.rect())
        self.main_window.save_data()
        self.main_window.sync_selection_from_scene(self.box_id)
        
        super().mouseReleaseEvent(event)
    
    def itemChange(self, change, value):
        if change == qtw.QGraphicsItem.ItemSelectedChange and value == True:
            self.main_window.sync_selection_from_scene(self.box_id)
        return super().itemChange(change, value)

class AnnotationScene(qtw.QGraphicsScene):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.drawing_start = None
        self.current_temp_rect = None

    def mousePressEvent(self, event):
        if not self.main_window.is_drawing_mode:
            super().mousePressEvent(event)
            return

        self.drawing_start = event.scenePos()
        self.current_temp_rect = qtw.QGraphicsRectItem(qtc.QRectF(self.drawing_start, self.drawing_start))
        self.current_temp_rect.setPen(qtg.QPen(qtg.Qt.yellow, 1, qtg.Qt.DashLine))
        self.addItem(self.current_temp_rect)

    def mouseMoveEvent(self, event):
        if self.drawing_start:
            rect = qtc.QRectF(self.drawing_start, event.scenePos()).normalized()
            self.current_temp_rect.setRect(rect)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drawing_start:
            rect = self.current_temp_rect.rect()
            self.removeItem(self.current_temp_rect)
            self.drawing_start = None
            
            if rect.width() > 5 and rect.height() > 5:
                self.main_window.finalize_drawing(rect)
            else:
                self.main_window.cancel_drawing()
        else:
            super().mouseReleaseEvent(event)

# =============================================================================
# 4. MAIN WINDOW
# =============================================================================
class MainWindow(qtw.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Annotation Tool - Final Workflow")
        self.resize(1300, 800)
        
        self.manager = AnnotationManager()
        self.current_image_folder = ""
        self.json_folder = ""
        self.current_frame_idx = -1
        self.frame_files = []
        
        self.is_drawing_mode = False
        self.pending_draw_data = None
        self.classes_map = {} # {name: id}
        self.id_to_name_map = {} # {id: name}

        self.setup_ui()
        self.load_classes_config()
        
        # Shortcuts
        qtg.QShortcut(qtg.QKeySequence("Del"), self, self.delete_selected_box)
        qtg.QShortcut(qtg.QKeySequence("D"), self, self.next_frame)
        qtg.QShortcut(qtg.QKeySequence("A"), self, self.prev_frame)

    def setup_ui(self):
        main_widget = qtw.QWidget()
        self.setCentralWidget(main_widget)
        layout = qtw.QHBoxLayout(main_widget)
        
        # LEFT: Graphics View
        self.scene = AnnotationScene(self)
        self.view = qtw.QGraphicsView(self.scene)
        self.view.setRenderHint(qtg.QPainter.Antialiasing)
        layout.addWidget(self.view, stretch=4)
        
        # RIGHT: Controls
        sidebar = qtw.QWidget()
        sidebar.setFixedWidth(300)
        sidebar_layout = qtw.QVBoxLayout(sidebar)
        layout.addWidget(sidebar, stretch=1)
        
        # 1. Navigation
        sidebar_layout.addWidget(qtw.QLabel("<b>Frame Controls</b>"))
        btn_open = qtw.QPushButton("Open Folder")
        btn_open.clicked.connect(self.open_folder)
        sidebar_layout.addWidget(btn_open)
        
        self.lbl_filename = qtw.QLabel("No Image")
        sidebar_layout.addWidget(self.lbl_filename)
        
        nav_layout = qtw.QHBoxLayout()
        btn_prev = qtw.QPushButton("<< Prev (A)")
        btn_prev.clicked.connect(self.prev_frame)
        btn_next = qtw.QPushButton("Next (D) >>")
        btn_next.clicked.connect(self.next_frame)
        nav_layout.addWidget(btn_prev)
        nav_layout.addWidget(btn_next)
        sidebar_layout.addLayout(nav_layout)
        sidebar_layout.addWidget(self.create_hline())

        # 2. Status / Action
        sidebar_layout.addWidget(qtw.QLabel("<b>Actions</b>"))
        self.btn_create = qtw.QPushButton("Create New Object")
        self.btn_create.setStyleSheet("background-color: #2A82DA; font-weight: bold; padding: 5px;")
        self.btn_create.clicked.connect(self.start_creation_flow)
        sidebar_layout.addWidget(self.btn_create)
        
        self.lbl_status = qtw.QLabel("Mode: View")
        self.lbl_status.setStyleSheet("color: grey;")
        sidebar_layout.addWidget(self.lbl_status)
        sidebar_layout.addWidget(self.create_hline())

        # 3. Two-Section Object Lists
        # SECTION A: Frame Objects
        sidebar_layout.addWidget(qtw.QLabel("<b>Objects in Frame</b>"))
        self.list_frame_objects = qtw.QListWidget()
        self.list_frame_objects.itemClicked.connect(self.on_frame_list_item_clicked)
        # Limit height so Folder list is visible
        self.list_frame_objects.setMaximumHeight(200) 
        sidebar_layout.addWidget(self.list_frame_objects)
        
        btn_del = qtw.QPushButton("Delete Selected")
        btn_del.clicked.connect(self.delete_selected_box)
        sidebar_layout.addWidget(btn_del)
        
        sidebar_layout.addWidget(self.create_hline())
        
        # SECTION B: Folder Objects
        sidebar_layout.addWidget(qtw.QLabel("<b>All Detected Objects (Folder)</b>"))
        self.list_folder_objects = qtw.QListWidget()
        self.list_folder_objects.setToolTip("Click an object here to draw it on the current frame.")
        self.list_folder_objects.itemClicked.connect(self.on_folder_list_item_clicked)
        sidebar_layout.addWidget(self.list_folder_objects)
        btn_interp = qtw.QPushButton("Interpolate Selected Track")
        btn_interp.setToolTip("Fills missing frames between annotated keyframes for the selected track.")
        btn_interp.clicked.connect(self.run_interpolation)
        sidebar_layout.addWidget(btn_interp)

    def create_hline(self):
        line = qtw.QFrame()
        line.setFrameShape(qtw.QFrame.HLine)
        line.setFrameShadow(qtw.QFrame.Sunken)
        return line

    def load_classes_config(self):
        # Helper function to find the path
        def resource_path(relative_path):
            """ Get absolute path to resource, works for dev and for PyInstaller """
            try:
                # PyInstaller creates a temp folder and stores path in _MEIPASS
                base_path = sys._MEIPASS
            except Exception:
                base_path = os.path.abspath(".")
            return os.path.join(base_path, relative_path)

        # Use the helper to get the path
        path = resource_path("id_list.txt")
        
        # The rest is the same as before
        if os.path.exists(path):
            with open(path, "r") as f:
                for line in f:
                    if ',' in line:
                        parts = line.strip().split(',')
                        name = parts[0].strip()
                        try:
                            cid = int(parts[1].strip())
                            self.classes_map[name] = cid
                            self.id_to_name_map[cid] = name
                        except: pass

    # --- WORKFLOW LOGIC ---


    def run_interpolation(self):
        # 1. Get Selected Track from the Folder List (Bottom Right)
        item = self.list_folder_objects.currentItem()
        if not item:
            qtw.QMessageBox.warning(self, "Selection Error", "Please select a Track from the 'All Detected Objects' list.")
            return

        track_id = item.data(qtc.Qt.UserRole)

        # 2. Confirm Action
        reply = qtw.QMessageBox.question(
            self, "Confirm Interpolation", 
            f"This will fill gaps for Track {track_id} across the entire folder.\n"
            "Existing annotations for this track will act as keyframes.\n\n"
            "Proceed?",
            qtw.QMessageBox.Yes | qtw.QMessageBox.No
        )

        if reply == qtw.QMessageBox.No: return

        # 3. Run Logic
        count = self.manager.interpolate_track(track_id, self.json_folder, self.frame_files)

        # 4. Feedback
        qtw.QMessageBox.information(self, "Success", f"Interpolation complete.\nAdded {count} new bounding boxes.")

        # 5. Reload current frame to see changes immediately
        self.load_frame()


    def start_creation_flow(self):
        """Open Dialog to get Class and ID for a brand new object."""
        if not self.frame_files: return
        
        dialog = CreateObjectDialog(self, self.classes_map, self.manager.next_suggestion_track_id)
        if dialog.exec():
            cid, tid, cname = dialog.get_data()
            self.prepare_to_draw(cid, tid, cname)

    def on_folder_list_item_clicked(self, item):
        """User clicked an existing object from the folder list -> Ready to draw that object."""
        if not self.frame_files: return
        
        tid = item.data(qtc.Qt.UserRole)
        # Retrieve class ID from manager's record
        cid = self.manager.folder_unique_tracks.get(tid, -1)
        cname = self.id_to_name_map.get(cid, "Unknown")
        
        self.prepare_to_draw(cid, tid, cname)

    def prepare_to_draw(self, cid, tid, cname):
        self.pending_draw_data = {'class': cid, 'track': tid}
        self.set_drawing_mode(True)
        self.lbl_status.setText(f"Mode: Drawing [Track {tid} - {cname}]")
        self.lbl_status.setStyleSheet("color: #2A82DA; font-weight: bold;")

    def set_drawing_mode(self, enabled):
        self.is_drawing_mode = enabled
        if enabled:
            self.view.setCursor(qtg.Qt.CrossCursor)
            # Deselect current items to avoid confusion
            for item in self.scene.selectedItems(): item.setSelected(False)
        else:
            self.view.setCursor(qtg.Qt.ArrowCursor)
            self.lbl_status.setText("Mode: View")
            self.lbl_status.setStyleSheet("color: grey;")

    def finalize_drawing(self, rect):
        if self.pending_draw_data:
            cid = self.pending_draw_data['class']
            tid = self.pending_draw_data['track']
            
            box_id = self.manager.add_box(rect, cid, tid)
            self.draw_box_on_scene(box_id, rect, cid, tid)
            
            self.save_data()
            self.refresh_lists()
            
            self.pending_draw_data = None
            self.set_drawing_mode(False)

    def cancel_drawing(self):
        self.pending_draw_data = None
        self.set_drawing_mode(False)

    # --- UI SYNC ---

    def refresh_lists(self):
        # 1. Refresh Frame List
        self.list_frame_objects.clear()
        for bid, data in self.manager.boxes.items():
            cid = data.get('class')
            tid = data.get('track_id')
            cname = self.id_to_name_map.get(cid, "Unknown")
            item = qtw.QListWidgetItem(f"Track {tid} : {cname}")
            item.setData(qtc.Qt.UserRole, bid)
            pix = qtg.QPixmap(16, 16)
            pix.fill(get_color_for_id(tid))
            item.setIcon(qtg.QIcon(pix))
            self.list_frame_objects.addItem(item)

        # 2. Refresh Folder List (Master List)
        # Note: We don't clear this every frame usually, but to ensure new tracks created 
        # in this frame appear immediately, we reload it from manager.folder_unique_tracks
        self.list_folder_objects.clear()
        # Sort by Track ID
        sorted_tracks = sorted(self.manager.folder_unique_tracks.items())
        
        for tid, cid in sorted_tracks:
            cname = self.id_to_name_map.get(cid, "Unknown")
            item = qtw.QListWidgetItem(f"Track {tid} : {cname}")
            item.setData(qtc.Qt.UserRole, tid)
            pix = qtg.QPixmap(16, 16)
            pix.fill(get_color_for_id(tid))
            item.setIcon(qtg.QIcon(pix))
            self.list_folder_objects.addItem(item)

    def sync_selection_from_scene(self, box_id):
        """Scene Box Clicked -> Select in Frame List."""
        for i in range(self.list_frame_objects.count()):
            item = self.list_frame_objects.item(i)
            if item.data(qtc.Qt.UserRole) == box_id:
                self.list_frame_objects.setCurrentItem(item)
                break

    def on_frame_list_item_clicked(self, item):
        """Frame List Item Clicked -> Select in Scene."""
        box_id = item.data(qtc.Qt.UserRole)
        for gitem in self.scene.items():
            if isinstance(gitem, BoxItem):
                gitem.setSelected(False)
        for gitem in self.scene.items():
            if isinstance(gitem, BoxItem) and gitem.box_id == box_id:
                gitem.setSelected(True)
                return

    # --- STANDARD FILE OPS ---

    def open_folder(self):
        folder = qtw.QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if not folder: return
        
        self.current_image_folder = folder
        
        # --- PATH CALCULATION UPDATE START ---
        # 1. Get the parent directory of the selected folder
        # Example: /mnt/.../Got10k/train -> /mnt/.../Got10k
        parent_dir = os.path.dirname(folder)
        
        # 2. Define the root annotations folder
        # Example: /mnt/.../Got10k/annotations
        annotations_root = os.path.join(parent_dir, "annotations")
        
        # 3. Define the specific sequence folder with _json suffix
        # Example: GOT-10k_Train_000005 -> GOT-10k_Train_000005_json
        sequence_name = os.path.basename(folder)
        self.json_folder = os.path.join(annotations_root, sequence_name + "_json")
        
        # 4. Create the directories if they don't exist
        os.makedirs(self.json_folder, exist_ok=True)
        # --- PATH CALCULATION UPDATE END ---
        
        # Scan folder for existing tracks (Scans the new json_folder path)
        self.manager.scan_folder(self.json_folder)
        
        # Load Images
        files = sorted(os.listdir(folder))
        self.frame_files = [f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if self.frame_files:
            self.current_frame_idx = 0
            self.load_frame()

    
    def load_frame(self):
        filename = self.frame_files[self.current_frame_idx]
        self.lbl_filename.setText(f"{filename} ({self.current_frame_idx + 1}/{len(self.frame_files)})")
        
        path = os.path.join(self.current_image_folder, filename)
        pixmap = qtg.QPixmap(path)
        self.scene.clear()
        self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())
        self.view.fitInView(self.scene.sceneRect(), qtc.Qt.KeepAspectRatio)
        
        json_path = os.path.join(self.json_folder, os.path.splitext(filename)[0] + ".json")
        self.manager.load_from_file(json_path)
        
        for bid, data in self.manager.boxes.items():
            coords = data['box']
            rect = qtc.QRectF(coords[0], coords[1], coords[2]-coords[0], coords[3]-coords[1])
            self.draw_box_on_scene(bid, rect, data.get('class'), data.get('track_id'))
            
        self.refresh_lists()

    def draw_box_on_scene(self, bid, rect, cid, tid):
        item = BoxItem(rect, bid, tid, self.manager, self)
        self.scene.addItem(item)

    def next_frame(self):
        if self.current_frame_idx < len(self.frame_files) - 1:
            self.current_frame_idx += 1
            self.load_frame()

    def prev_frame(self):
        if self.current_frame_idx > 0:
            self.current_frame_idx -= 1
            self.load_frame()

    def save_data(self):
        self.manager.save_to_file()
        
    def delete_selected_box(self):
        items = self.scene.selectedItems()
        if not items: return
        for item in items:
            if isinstance(item, BoxItem):
                self.manager.delete_box(item.box_id)
                self.scene.removeItem(item)
        self.save_data()
        self.refresh_lists()

if __name__ == "__main__":
    app = qtw.QApplication(sys.argv)
    apply_dark_theme(app)
    mw = MainWindow()
    mw.show()
    sys.exit(app.exec())