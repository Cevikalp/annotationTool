import sys
import os
import json
import random
from pathlib import Path
import threading
from ultralytics import YOLO

from PySide6 import QtCore as qtc
from PySide6 import QtGui as qtg
from PySide6 import QtWidgets as qtw

# =============================================================================
# 1. HELPER CLASSES & UTILS
# =============================================================================

# Helper function to find the path
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

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


    def rebuild_track_cache(self, json_folder):
        """
        Clears and rebuilds the folder_unique_tracks map by scanning all JSON files.
        This ensures that if a Track ID is removed from the last frame it existed in,
        it disappears from the sidebar immediately.
        """
        self.folder_unique_tracks = {}
        
        if not os.path.exists(json_folder): return

        for filename in os.listdir(json_folder):
            if not filename.endswith(".json") or filename.startswith("classes"): 
                continue
            
            path = os.path.join(json_folder, filename)
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                
                for val in data.values():
                    tid = val.get('track_id')
                    cls = val.get('class')
                    # We just need to know it exists. 
                    # If multiple frames have different classes for ID X (rare error), last one wins.
                    self.folder_unique_tracks[tid] = cls
            except: pass

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

    def check_track_used_globally(self, track_id, json_folder):
        """
        Scans all JSON files to see if track_id exists ANYWHERE.
        Returns True immediately if found, False if scanned all and not found.
        """
        if not os.path.exists(json_folder): return False
        
        for filename in os.listdir(json_folder):
            if not filename.endswith(".json") or filename.startswith("classes"): 
                continue
            
            path = os.path.join(json_folder, filename)
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    for entry in data.values():
                        if entry.get('track_id') == track_id:
                            return True # Found it! Track is still alive.
            except: pass
            
        return False # Track is completely gone.
    
    def delete_box(self, box_id):
        """
        Deletes a box and returns its Track ID (so we can check if the track is empty later).
        """
        if box_id in self.boxes:
            tid = self.boxes[box_id].get('track_id')
            del self.boxes[box_id]
            return tid
        return None

        
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
    def update_track_id_globally(self, old_tid, new_tid, json_folder):
        """
        Renames a Track ID in ALL JSON files in the folder.
        """
        if old_tid == new_tid: return 0
        
        count = 0
        # Scan all files
        for filename in os.listdir(json_folder):
            if not filename.endswith(".json") or filename.startswith("classes"): 
                continue
            
            path = os.path.join(json_folder, filename)
            changed = False
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                
                # Check and Modify
                for key, val in data.items():
                    if val.get('track_id') == old_tid:
                        val['track_id'] = new_tid
                        changed = True
                        count += 1
                
                # Save back if changed
                if changed:
                    with open(path, 'w') as f:
                        json.dump(data, f, indent=4)
            except: pass
            
        return count

    def update_class_globally(self, track_id, new_class, json_folder):
        """
        Changes the Class ID for a specific Track ID in ALL JSON files.
        """
        count = 0
        for filename in os.listdir(json_folder):
            if not filename.endswith(".json") or filename.startswith("classes"): 
                continue
            
            path = os.path.join(json_folder, filename)
            changed = False
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                
                for key, val in data.items():
                    if val.get('track_id') == track_id:
                        val['class'] = new_class
                        changed = True
                        count += 1
                
                if changed:
                    with open(path, 'w') as f:
                        json.dump(data, f, indent=4)
            except: pass
        return count

    def swap_track_id_globally(self, id1, id2, json_folder):
        """
        Swaps two Track IDs across ALL files.
        Track A becomes Track B, and Track B becomes Track A.
        """
        if id1 == id2: return 0
        
        count = 0
        for filename in os.listdir(json_folder):
            if not filename.endswith(".json") or filename.startswith("classes"): 
                continue
            
            path = os.path.join(json_folder, filename)
            changed = False
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                
                for key, val in data.items():
                    current_id = val.get('track_id')
                    
                    # The Swap Logic
                    if current_id == id1:
                        val['track_id'] = id2
                        changed = True
                        count += 1
                    elif current_id == id2:
                        val['track_id'] = id1
                        changed = True
                        count += 1
                
                if changed:
                    with open(path, 'w') as f:
                        json.dump(data, f, indent=4)
            except: pass
            
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

    def update_appearance(self, class_id, track_id):
        # 1. Update Internal IDs
        self.class_id = class_id
        self.track_id = track_id
        
        # 2. Update Color (Safe)
        # This uses your existing set_color method
        if hasattr(self, 'set_color'):
            self.set_color(track_id)
        
        # 3. Get Class Name (SAFE Check)
        cls_name = str(class_id)
        
        # Check if 'manager' exists before trying to use it
        if hasattr(self, 'manager') and self.manager:
            try:
                # Try to get the real name from the manager map
                if hasattr(self.manager, 'id_to_name_map'):
                    cls_name = self.manager.id_to_name_map.get(class_id, str(class_id))
            except: pass

        # 4. Update Text (Safe)
        if hasattr(self, 'text'):
            self.text.setPlainText(f"{track_id} : {cls_name}")
            
            # Optional: Add background color to text for readability
            # We need to find the color again safely
            try:
                # Assuming get_color_for_id is global or we can grab pen color
                color = self.pen().color() 
                self.text.setHtml(f'<div style="background-color: {color.name()}; color: white; padding: 2px;">{track_id} : {cls_name}</div>')
            except:
                pass

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


class YoloWorker(qtc.QThread):
    """
    Runs YOLO inference in a separate thread to prevent freezing the UI.
    """
    results_ready = qtc.Signal(list) # Emits a list of dicts: [{'box':..., 'class':...}, ...]

    def __init__(self, image_path, config_path):
        super().__init__()
        self.image_path = image_path
        self.config_path = config_path

    def run(self):
        # 1. Load Config
        # We use resource_path here just in case the config is also bundled
        if not os.path.exists(self.config_path):
            print("YOLO Config not found.")
            return

        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
        except: return

        model_name = config.get("model_path", "yolov11n.pt")
        mapping = config.get("mapping", {}) # "COCO_ID": "APP_ID"
        conf = config.get("conf_thres", 0.45)

        # 2. Load Model (Handle "Frozen" Path for Exe)
        # Check if the model file is bundled inside the executable (resource_path)
        # 'resource_path' must be defined globally in your script (as shown in Step 1)
        bundled_model_path = resource_path(model_name)
        
        if os.path.exists(bundled_model_path):
            # If we are running as an Exe and found the bundled file, use full path
            load_path = bundled_model_path
        else:
            # If running in Dev (or file missing), let Ultralytics download/cache it
            load_path = model_name

        try:
            model = YOLO(load_path)
        except Exception as e:
            print(f"Error loading model: {e}")
            return

        # 3. Run Inference
        # Force device='cpu' to prevent Quadro P5000 crash
        # verbose=False keeps the console clean
        try:
            results = model.predict(self.image_path, conf=conf, device='cpu', verbose=False)
        except Exception as e:
            print(f"Inference Error: {e}")
            return

        detected_objects = []

        # 4. Process Results
        for result in results:
            boxes = result.boxes
            for box in boxes:
                # YOLO coordinates
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls_id = int(box.cls[0].item())
                
                # Check Mapping
                # We cast cls_id to str because JSON keys are always strings
                if str(cls_id) in mapping:
                    app_class_id = int(mapping[str(cls_id)])
                    
                    detected_objects.append({
                        'box': [x1, y1, x2, y2],
                        'class': app_class_id
                    })

        self.results_ready.emit(detected_objects)


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


    def set_view_mode(self):
        """
        Resets the application state to standard View/Select mode.
        """
        # 1. Reset your existing flags
        self.is_drawing_mode = False
        self.pending_draw_data = None 

        self.view.setCursor(qtg.Qt.ArrowCursor)
        self.lbl_status.setText("Mode: View")
        self.lbl_status.setStyleSheet("color: grey;")

    def calculate_iou(self, boxA, boxB):
        # box: [x1, y1, x2, y2]
        # Determine the (x, y) coordinates of the intersection rectangle
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        # Compute the area of intersection rectangle
        interArea = max(0, xB - xA) * max(0, yB - yA)

        # Compute the area of both rectangles
        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

        # Compute the intersection over union
        iou = interArea / float(boxAArea + boxBArea - interArea)
        return iou

    def run_yolo_detection(self):
        if not self.frame_files: return
        if self.current_frame_idx > 0:
            # 1. Calculate path to previous frame's JSON
            prev_filename = self.frame_files[self.current_frame_idx - 1]
            prev_json_path = os.path.join(self.json_folder, os.path.splitext(prev_filename)[0] + ".json")
            
            # 2. Check if it exists and has content
            has_prev_data = False
            if os.path.exists(prev_json_path):
                try:
                    with open(prev_json_path, 'r') as f:
                        data = json.load(f)
                        if data: # If dict is not empty
                            has_prev_data = True
                except: pass
            
            # 3. Show Warning if missing
            if not has_prev_data:
                reply = qtw.QMessageBox.question(
                    self, "Gap Detected",
                    "The **Previous Frame** is not annotated (or empty).\n\n"
                    "Without the previous frame, 'Smart Matching' cannot work,\n"
                    "and YOLO will create NEW Track IDs for all objects.\n\n"
                    "Do you want to continue anyway?",
                    qtw.QMessageBox.Yes | qtw.QMessageBox.No
                )
                if reply == qtw.QMessageBox.No:
                    return
        
        # Determine paths
        image_path = os.path.join(self.current_image_folder, self.frame_files[self.current_frame_idx])
        
        # Find config in root (for dev) or resource path (for exe)
        # Use the same 'resource_path' logic you used for id_list.txt if needed
        root_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = resource_path("yolo_config.json")
        
        if not os.path.exists(config_path):
            qtw.QMessageBox.warning(self, "Config Missing", "Could not find 'yolo_config.json'.")
            return

        # Disable button to prevent double clicks
        self.btn_yolo.setEnabled(False)
        self.btn_yolo.setText("Detecting...")
        
        # Start Thread
        self.yolo_thread = YoloWorker(image_path, config_path)
        self.yolo_thread.results_ready.connect(self.on_yolo_finished)
        self.yolo_thread.finished.connect(self.yolo_thread.deleteLater)
        self.yolo_thread.start()

    def on_yolo_finished(self, detections):
        self.btn_yolo.setEnabled(True)
        self.btn_yolo.setText("Auto-Detect (YOLO)")
        
        if not detections:
            qtw.QMessageBox.information(self, "YOLO", "No matching objects found.")
            return

        # --- STEP 0: FILTER AGAINST CURRENT MANUAL ANNOTATIONS (The Fix) ---
        # If the user already drew a "Bicycle" here, don't let YOLO add another one on top.
        
        # 1. Get all boxes currently on the screen
        existing_boxes = list(self.manager.boxes.values()) # [{'box':..., 'class':...}, ...]
        
        unique_detections = []
        
        for det in detections:
            is_duplicate = False
            for existing in existing_boxes:
                # Check Overlap
                iou = self.calculate_iou(det['box'], existing['box'])
                
                # Check Class (Optional: You might want to block even if class is different if overlap is huge)
                # For now, we only block if it's the SAME class or very high overlap
                if iou > 0.5 and det['class'] == existing['class']:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_detections.append(det)
        
        # Update our list to only use the non-duplicate ones
        detections = unique_detections

        if not detections:
            self.lbl_status.setText("YOLO: No NEW objects found (ignored duplicates).")
            return


        # --- STEP 1: FILTER INTERNAL OVERLAPS (NMS) ---
        # (Same as before: remove YOLO overlapping with other YOLO boxes)
        indices_to_drop = set()
        for i in range(len(detections)):
            if i in indices_to_drop: continue
            for j in range(i + 1, len(detections)):
                if j in indices_to_drop: continue
                iou = self.calculate_iou(detections[i]['box'], detections[j]['box'])
                if iou > 0.5:
                    indices_to_drop.add(j)

        final_detections = [d for k, d in enumerate(detections) if k not in indices_to_drop]

        # --- STEP 2: LOAD PREVIOUS FRAME (Smart Matching) ---
        prev_frame_boxes = [] 
        if self.current_frame_idx > 0:
            prev_filename = self.frame_files[self.current_frame_idx - 1]
            prev_json_path = os.path.join(self.json_folder, os.path.splitext(prev_filename)[0] + ".json")
            if os.path.exists(prev_json_path):
                try:
                    with open(prev_json_path, 'r') as f:
                        data = json.load(f)
                        for v in data.values():
                            if 'box' in v and 'track_id' in v:
                                prev_frame_boxes.append(v)
                except: pass

        count = 0
        
        # --- STEP 3: CREATE BOXES ---
        for item in final_detections:
            new_box = item['box']
            new_class = item['class']
            assigned_track_id = -1
            
            # Match Logic
            best_iou = 0.0
            best_match_id = -1
            best_match_class = -1
            
            for prev in prev_frame_boxes:
                iou = self.calculate_iou(new_box, prev['box'])
                if iou > best_iou:
                    best_iou = iou
                    best_match_id = prev['track_id']
                    best_match_class = prev['class']
            
            # Sticky Class Logic
            if best_iou > 0.3:
                assigned_track_id = best_match_id
                new_class = best_match_class 
            else:
                assigned_track_id = self.manager.next_suggestion_track_id
                self.manager.next_suggestion_track_id += 1
            
            rect = qtc.QRectF(new_box[0], new_box[1], new_box[2]-new_box[0], new_box[3]-new_box[1])
            box_id = self.manager.add_box(rect, new_class, assigned_track_id)
            self.draw_box_on_scene(box_id, rect, new_class, assigned_track_id)
            count += 1
            
        self.save_data()
        self.refresh_lists()
        self.lbl_status.setText(f"YOLO: Added {count} new boxes.")

    def run_interpolation_all(self):
        """
        Runs interpolation for EVERY track ID found in the current sequence.
        """
        if not self.manager.folder_unique_tracks:
            qtw.QMessageBox.information(self, "Info", "No tracks found in this folder to interpolate.")
            return

        # 1. Warning
        reply = qtw.QMessageBox.question(
            self, "Confirm Bulk Interpolation", 
            "WARNING: This will attempt to fill gaps for ALL tracks in the folder.\n\n"
            "This operation cannot be easily undone.\n"
            "Are you sure you want to proceed?",
            qtw.QMessageBox.Yes | qtw.QMessageBox.No
        )
        
        if reply == qtw.QMessageBox.No: return

        # 2. Loop and Execute
        total_added = 0
        tracks_processed = 0
        
        # Get all unique IDs
        all_ids = list(self.manager.folder_unique_tracks.keys())
        
        # Optional: Show a progress dialog if you have many tracks
        progress = qtw.QProgressDialog("Interpolating tracks...", "Cancel", 0, len(all_ids), self)
        progress.setWindowModality(qtc.Qt.WindowModal)
        
        for i, track_id in enumerate(all_ids):
            if progress.wasCanceled():
                break
            
            # Call the existing manager logic
            count = self.manager.interpolate_track(track_id, self.json_folder, self.frame_files)
            total_added += count
            tracks_processed += 1
            progress.setValue(i + 1)
        
        # 3. Final Feedback
        self.load_frame() # Refresh current view
        qtw.QMessageBox.information(self, "Complete", f"Processed {tracks_processed} tracks.\nAdded {total_added} new boxes total.")

    def show_frame_list_menu(self, pos):
        """ Context menu for the top list (Current Frame Objects) """
        item = self.list_frame_objects.itemAt(pos)
        if not item: return

        # Get Box ID from user role
        box_id = item.data(qtc.Qt.UserRole)
        box_data = self.manager.boxes.get(box_id)
        if not box_data: return

        menu = qtw.QMenu(self)
        
        # Actions
        action_edit_class = menu.addAction("Edit Class (This Frame Only)")
        action_edit_track = menu.addAction("Edit Track ID (This Frame Only)")
        # action_swap_track = menu.addAction("Swap Track ID (This Frame)") # <--- NEW

        action = menu.exec(self.list_frame_objects.mapToGlobal(pos))

        if action == action_edit_class:
            self.edit_class_single(box_id, box_data)
        elif action == action_edit_track:
            self.edit_track_single(box_id, box_data)
        # elif action == action_swap_track:
        #     self.swap_track_single(box_id, box_data)  # <--- NEW

    def show_global_list_menu(self, pos):
        """ Context menu for the bottom list (All Tracks Summary) """
        item = self.list_folder_objects.itemAt(pos)
        if not item: return

        # The bottom list stores Track ID in UserRole
        track_id = item.data(qtc.Qt.UserRole)

        menu = qtw.QMenu(self)
        action_edit_class_all = menu.addAction("Edit Class (ALL Frames)")
        action_edit_track_all = menu.addAction("Edit Track ID (ALL Frames)")
        action_swap_track_all = menu.addAction("Swap Track ID (Global)") # <--- NEW
        
        action = menu.exec(self.list_folder_objects.mapToGlobal(pos))
        
        if action == action_edit_class_all:
            self.edit_class_global(track_id)
        elif action == action_edit_track_all:
            self.edit_track_global(track_id)
        elif action == action_swap_track_all:
            self.swap_track_global(track_id) # <--- NEW

    # --- Single Frame Edits ---
    def edit_class_single(self, box_id, box_data):
        current_cls = box_data['class']
        
        # Prepare List
        items = []
        sorted_ids = sorted(self.id_to_name_map.keys())
        current_index = 0
        for i, cid in enumerate(sorted_ids):
            name = self.id_to_name_map[cid]
            items.append(f"{cid}: {name}")
            if cid == current_cls:
                current_index = i
        
        val_str, ok = qtw.QInputDialog.getItem(self, "Edit Class", "Select New Class:", items, current_index, False)
        
        if ok and val_str:
            new_class_id = int(val_str.split(':')[0])
            if new_class_id != current_cls:
                # 1. Update Memory
                self.manager.boxes[box_id]['class'] = new_class_id
                
                # 2. Update Scene
                for item in self.scene.items():
                    if isinstance(item, BoxItem) and item.box_id == box_id:
                        item.update_appearance(new_class_id, box_data['track_id'])
                        break
                
                # 3. FIX: Update Global Cache so bottom list updates
                self.manager.folder_unique_tracks[box_data['track_id']] = new_class_id
                
                self.save_data()
                self.refresh_lists()
    

    def edit_track_single(self, box_id, box_data):
        current_tid = box_data['track_id']
        val, ok = qtw.QInputDialog.getInt(self, "Edit Track ID", "New Track ID:", current_tid, 1, 10000)
        
        if ok and val != current_tid:
            # 1. Update Memory
            self.manager.boxes[box_id]['track_id'] = val
            
            # 2. Update Scene
            for item in self.scene.items():
                if isinstance(item, BoxItem) and item.box_id == box_id:
                    item.update_appearance(box_data['class'], val)
                    break
            
            # 3. FIX: Add new Track ID to Global Cache
            self.manager.folder_unique_tracks[val] = box_data['class']
            # (Optional: We don't delete the old ID from cache because it might exist in other frames)

        self.save_data()
        self.manager.rebuild_track_cache(self.json_folder)
        self.refresh_lists()


    # --- Global Edits (The Heavy Lifters) ---
    def edit_class_global(self, track_id):
        # Prepare List
        items = []
        sorted_ids = sorted(self.id_to_name_map.keys())
        for cid in sorted_ids:
            name = self.id_to_name_map[cid]
            items.append(f"{cid}: {name}")
            
        val_str, ok = qtw.QInputDialog.getItem(self, "Global Class Update", 
                                               f"Change Class for Track {track_id} in ALL frames to:", 
                                               items, 0, False)
        
        if ok and val_str:
            new_class_id = int(val_str.split(':')[0])
            
            # 1. Update Files
            count = self.manager.update_class_globally(track_id, new_class_id, self.json_folder)
            
            # 2. FIX: Update Global Cache
            self.manager.folder_unique_tracks[track_id] = new_class_id
            
            # 3. Reload
            self.load_frame() # This calls refresh_lists()
            qtw.QMessageBox.information(self, "Updated", f"Updated class for {count} boxes across the video.")
        self.set_view_mode()


    def edit_track_global(self, old_track_id):
        val, ok = qtw.QInputDialog.getInt(self, "Global Track Update", 
                                          f"Rename Track {old_track_id} in ALL frames to:", 
                                          old_track_id, 1, 10000)
        if not ok or val == old_track_id: return

        if self.manager.check_track_used_globally(val, self.json_folder):
            reply = qtw.QMessageBox.question(self, "Conflict Warning", 
                                             f"Track ID {val} already exists.\nMerge?", 
                                             qtw.QMessageBox.Yes | qtw.QMessageBox.No)
            if reply == qtw.QMessageBox.No: return

        # 1. Update Files
        count = self.manager.update_track_id_globally(old_track_id, val, self.json_folder)
        
        # 2. FIX: Update Global Cache (Swap Keys)
        if old_track_id in self.manager.folder_unique_tracks:
            cls = self.manager.folder_unique_tracks[old_track_id]
            del self.manager.folder_unique_tracks[old_track_id] # Remove old
            self.manager.folder_unique_tracks[val] = cls        # Add new



    # def swap_track_single(self, source_box_id, source_data_passed):
    #     # 1. Safety: Re-fetch the latest source data from manager
    #     if source_box_id not in self.manager.boxes: return
    #     source_data = self.manager.boxes[source_box_id]
        
    #     current_id = int(source_data['track_id'])
        
    #     # 2. Ask for Target ID
    #     target_id, ok = qtw.QInputDialog.getInt(self, "Swap Track ID (Frame)", 
    #                                             f"Swap Track {current_id} with:", 
    #                                             current_id + 1, 1, 10000)
    #     if not ok or target_id == current_id: return

    #     # 3. ROBUST FIND: Find the object that owns "Target ID"
    #     target_box_id = None
    #     for bids, bdata in self.manager.boxes.items():
    #         # Skip the source box itself
    #         if bids == source_box_id: continue
            
    #         # Force Integer Comparison (Fixes the "Not Found" bug)
    #         try:
    #             if int(bdata.get('track_id')) == int(target_id):
    #                 target_box_id = bids
    #                 break
    #         except: continue
        
    #     # 4. Perform the Swap
    #     if target_box_id:
    #         # --- CASE A: Both exist. SWAP. ---
    #         target_data = self.manager.boxes[target_box_id]
    #         target_cls = target_data['class']
    #         source_cls = source_data['class']
            
    #         # Update Data Memory
    #         self.manager.boxes[source_box_id]['track_id'] = int(target_id)
    #         self.manager.boxes[target_box_id]['track_id'] = int(current_id)
            
    #         # Update Visuals
    #         for item in self.scene.items():
    #             if isinstance(item, BoxItem):
    #                 if item.box_id == source_box_id:
    #                     item.update_appearance(source_cls, int(target_id))
    #                 elif item.box_id == target_box_id:
    #                     item.update_appearance(target_cls, int(current_id))
            
    #         qtw.QMessageBox.information(self, "Swapped", f"Swapped Track {current_id} <-> {target_id} in this frame.")
        
    #     else:
    #         # --- CASE B: Target not in frame. RENAME. ---
    #         # This is valid if the user wants to take ID 5 and make it ID 99 (and ID 99 isn't used yet)
    #         self.manager.boxes[source_box_id]['track_id'] = int(target_id)
            
    #         for item in self.scene.items():
    #             if isinstance(item, BoxItem) and item.box_id == source_box_id:
    #                 item.update_appearance(source_data['class'], int(target_id))
            
    #         qtw.QMessageBox.information(self, "Renamed", f"Track {target_id} was not found in this frame.\nRenamed {current_id} to {target_id} instead.")

    #     # 5. Save & Reset
    #     self.save_data()
    #     self.manager.rebuild_track_cache(self.json_folder)
    #     self.refresh_lists()
    #     self.set_view_mode()

    def swap_track_global(self, id1):
        # 1. Ask for Target ID
        id2, ok = qtw.QInputDialog.getInt(self, "Swap Track ID (Global)", 
                                          f"Swap Track {id1} globally with:", 
                                          id1 + 1, 1, 10000)
        # Check if cancelled or same ID
        if not ok or id1 == id2: return

        # 2. Update Files
        count = self.manager.swap_track_id_globally(id1, id2, self.json_folder)
        
        # 3. Update Global Cache (Swap Keys)
        cls1 = self.manager.folder_unique_tracks.get(id1)
        cls2 = self.manager.folder_unique_tracks.get(id2)
        
        # Move Class from ID1 to ID2
        if cls1 is not None:
            self.manager.folder_unique_tracks[id2] = cls1
        else:
            if id2 in self.manager.folder_unique_tracks:
                del self.manager.folder_unique_tracks[id2]

        # Move Class from ID2 to ID1
        if cls2 is not None:
            self.manager.folder_unique_tracks[id1] = cls2
        else:
             if id1 in self.manager.folder_unique_tracks:
                del self.manager.folder_unique_tracks[id1]

        # 4. Reload
        self.load_frame()
        
        # FIX: Use 'id1' and 'id2' here (not old_track_id or val)
        qtw.QMessageBox.information(self, "Swapped", f"Swapped IDs {id1} and {id2} in {count} instances.")
        
        self.set_view_mode()

    
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
        self.list_frame_objects.setContextMenuPolicy(qtc.Qt.CustomContextMenu)  # <--- ENABLE RIGHT CLICK
        self.list_frame_objects.customContextMenuRequested.connect(self.show_frame_list_menu) # <--- CONNECT
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
        self.list_folder_objects.setContextMenuPolicy(qtc.Qt.CustomContextMenu) # <--- ENABLE RIGHT CLICK
        self.list_folder_objects.customContextMenuRequested.connect(self.show_global_list_menu) # <--- CONNECT
        sidebar_layout.addWidget(self.list_folder_objects)

        interp_layout = qtw.QHBoxLayout()
        
        # 1. Button: Selected
        self.btn_interp = qtw.QPushButton("Interp. Selected")
        self.btn_interp.setToolTip("Interpolate only the currently selected track.")
        self.btn_interp.clicked.connect(self.run_interpolation)
        interp_layout.addWidget(self.btn_interp)

        # 2. Button: ALL
        self.btn_interp_all = qtw.QPushButton("Interp. ALL")
        self.btn_interp_all.setToolTip("Interpolate ALL tracks in this folder (with confirmation).")
        self.btn_interp_all.setStyleSheet("background-color: #D65A31; color: white; font-weight: bold;")
        self.btn_interp_all.clicked.connect(self.run_interpolation_all)
        interp_layout.addWidget(self.btn_interp_all)

        # Add the horizontal layout to the main sidebar
        sidebar_layout.addLayout(interp_layout)
        self.btn_yolo = qtw.QPushButton("Auto-Detect (YOLO)")
        self.btn_yolo.setStyleSheet("background-color: #6A2C70; font-weight: bold; padding: 5px;")
        self.btn_yolo.clicked.connect(self.run_yolo_detection)
        sidebar_layout.addWidget(self.btn_yolo)


    def create_hline(self):
        line = qtw.QFrame()
        line.setFrameShape(qtw.QFrame.HLine)
        line.setFrameShadow(qtw.QFrame.Sunken)
        return line

    def load_classes_config(self):
        

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
        # reply = qtw.QMessageBox.question(
        #     self, "Confirm Interpolation", 
        #     f"This will fill gaps for Track {track_id} across the entire folder.\n"
        #     "Existing annotations for this track will act as keyframes.\n\n"
        #     "Proceed?",
        #     qtw.QMessageBox.Yes | qtw.QMessageBox.No
        # )

        # if reply == qtw.QMessageBox.No: return

        # 3. Run Logic
        count = self.manager.interpolate_track(track_id, self.json_folder, self.frame_files)

        # 4. Feedback
        qtw.QMessageBox.information(self, "Success", f"Interpolation complete.\nAdded {count} new bounding boxes.")

        # 5. Reload current frame to see changes immediately
        self.load_frame()
        self.set_view_mode()


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
        
        deleted_tracks = set()

        # 1. Delete from Memory
        for item in items:
            if isinstance(item, BoxItem):
                tid = self.manager.delete_box(item.box_id)
                if tid is not None:
                    deleted_tracks.add(tid)
                self.scene.removeItem(item)
        
        # 2. Save to Disk immediately
        self.save_data()
        
        # 3. Check for "Extinct" Tracks
        for tid in deleted_tracks:
            still_in_current_frame = False
            for data in self.manager.boxes.values():
                if data.get('track_id') == tid:
                    still_in_current_frame = True
                    break
            
            if not still_in_current_frame:
                exists_globally = self.manager.check_track_used_globally(tid, self.json_folder)
                if not exists_globally:
                    if tid in self.manager.folder_unique_tracks:
                        del self.manager.folder_unique_tracks[tid]

        # --- 4. RECALCULATE NEXT ID (The Fix) ---
        # We look at all tracks currently existing in the folder.
        # The next suggestion should be (Highest_ID + 1).
        if self.manager.folder_unique_tracks:
            # Ensure keys are integers for correct max() calculation
            existing_ids = [int(k) for k in self.manager.folder_unique_tracks.keys()]
            max_id = max(existing_ids)
            self.manager.next_suggestion_track_id = max_id + 1
        else:
            # If folder is empty, reset to 1
            self.manager.next_suggestion_track_id = 1

        # 5. Refresh UI
        self.refresh_lists()
        
if __name__ == "__main__":
    app = qtw.QApplication(sys.argv)
    apply_dark_theme(app)
    mw = MainWindow()
    mw.show()
    sys.exit(app.exec())