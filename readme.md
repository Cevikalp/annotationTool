# AI-Assisted Video Annotation Tool

A specialized desktop application for annotating objects in video frames with bounding boxes. This tool features **AI Auto-Detection (YOLOv11)**, **Linear Interpolation**, and **Smart Tracking** to significantly speed up the dataset creation process.

## 📦 Prerequisites & Installation

### Option A: Run from Executable (No Setup)
If you received the standalone `.exe` (Windows) or binary (Linux), you do not need to install anything.
1.  Double-click the file to launch.
2.  Ensure `id_list.txt` and `yolo_config.json` are in the same folder if you wish to customize them.

### Option B: Run from Source Code
1.  **Install Python:** Version 3.10 - 3.12 is recommended.
2.  **Install Libraries:**
    ```bash
    pip install PySide6 ultralytics
    ```
3.  **Run the App:**
    ```bash
    python annotation.py
    ```

---

## 🏗️ Building the Executable
To compile this tool into a standalone file for distribution, please refer to [BUILD.md](BUILD.md) for detailed instructions on using PyInstaller.

---

## 📖 User Guide

### 1. Getting Started
1.  **Load Images:** Click **"Open Image Folder"** and select the directory containing your video frames (images).
2.  **Load Annotations (Optional):** If you already have work saved, click **"Open Label Folder"**. If not, the app will automatically create a `labels` folder inside your image directory.
3.  **Navigation:**
    * `A` / `D` keys: Previous / Next Frame.
    * `W` / `S` keys: Jump 10 Frames Backward / Forward.
    * **Slider:** Drag to scrub through the video.

### 2. Manual Annotation
* **Draw a Box:** Left-click and drag on the image area.
* **Select Class:** A dialog will pop up asking for the **Class ID** (e.g., 1 for Person, 3 for Car). Refer to `id_list.txt` for codes.
* **Track IDs:** The tool automatically assigns a **Track ID**.
    * *Important:* If you are annotating the **same object** across multiple frames, ensure the **Track ID stays the same**.

### 3. AI Auto-Detection (YOLO)
The **"Auto-Detect (YOLO)"** button uses a neural network to find objects for you.

* **Smart Matching:** If the previous frame is annotated, YOLO will try to match new objects to existing Track IDs based on position.
* **Sticky Classes:** To prevent flickering (e.g., a bike changing to a motorbike), the tool trusts your previous manual labels over the AI's guess.
* **Duplicate Prevention:** If you manually draw a box, YOLO will not draw a duplicate box on top of it.
* **Warning:** Auto-detect works best when moving frame-by-frame. If you jump 50 frames and hit "Detect," the AI will lose track and assign new IDs.

### 4. Interpolation (The Time Saver)
Instead of drawing the same car 100 times, use Interpolation:

1.  **Frame 10:** Draw the car (Track ID 5).
2.  **Frame 50:** Go to frame 50, draw the car again (Track ID 5).
3.  **Action:** Click **"Interpolate Selected"** (or "Interpolate ALL").
4.  **Result:** The tool automatically fills frames 11-49 with bounding boxes connecting the two positions.

**Rules for Interpolation:**
* You must have the object annotated on at least **two different frames**.
* The **Track ID must match** (e.g., ID 5 on start frame, ID 5 on end frame).
* **Static Objects:** For background objects (parked cars), just annotate the first and last frame of the video and interpolate.

### 5. Editing & Deletion
* **Select:** Click on a box to select it (turns yellow).
* **Delete:** Press `Delete` key or click "Delete Selected".
* **Global Cleanup:** If you delete the *last remaining instance* of a Track ID, the tool automatically removes it from the "All Detected Objects" list to keep your workspace clean.

---

## ⚡ Shortcuts & Controls

| Action | Shortcut / Control |
| :--- | :--- |
| **Next Frame** | `D` or Right Arrow |
| **Prev Frame** | `A` or Left Arrow |
| **Fast Forward** | `W` (Jump 10 frames) |
| **Rewind** | `S` (Jump 10 frames) |
| **Delete Box** | `Delete` Key |
| **Select Box** | Left Click on Box |
| **Auto-Detect** | Click "Auto-Detect (YOLO)" |
| **Interpolate** | Click "Interpolate Selected" |

---

## ⚠️ Known Behaviors & Exceptions

### 1. "Ghost" Objects
If you mistakenly create "Track ID 99" on one frame and then delete it, the tool scans all files to ensure "Track 99" is truly gone. You won't see "Track 99" cluttering your list if no boxes exist.

### 2. Missing Previous Frame
If you skip a frame (e.g., Frame 1 -> Frame 3) and try to Auto-Detect on Frame 3, the tool will warn you. **Smart Matching requires the immediate previous frame** to be annotated to work correctly. Without it, YOLO will create brand new IDs.

### 3. Static Objects
Do not use "ID -1" for static objects. Instead, treat them as a normal track (e.g., "Car, ID 5") and use **Interpolation** from the first frame to the last frame. This provides better training data for models.

### 4. Customizing Classes
You can modify `id_list.txt` to change class names or IDs. The file format must be `classname , id`. Restart the app after saving changes.

### 5. GPU vs CPU
The tool is configured to run YOLO on the **CPU** by default. This ensures stability on all computers (including laptops) and avoids crashes related to older NVIDIA drivers (e.g., Quadro P5000 series). Performance on CPU is optimized using the YOLOv11n (Nano) model.