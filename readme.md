pip install PySide6
pip install pyinstaller

to compile on windows:
pyinstaller --noconsole --onefile --add-data "id_list.txt;." annotation.py

to compile on linux:
pyinstaller --noconsole --onefile --add-data "id_list.txt:." annotation