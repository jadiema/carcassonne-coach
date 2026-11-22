"""
🏰 carcassonne-coach — fabrique le paquet de l'extension (.xpi) à envoyer à Mozilla
=================================================================================
    python build_xpi.py            → carcassonne-coach-<version>.xpi

N'utilisez pas « web-ext build » : il ignore tous les fichiers .zip, donc
pyodide/python_stdlib.zip (la bibliothèque standard de Python), et le moteur
intégré au navigateur ne démarre plus (« Program terminated with exit(1) »).
"""
import json, os, sys, zipfile

FILES = ["manifest.json", "background.js", "probabilites.js", "content-script.js", "content-style.css",
         "popup.html", "popup.js", "livre.js", "welcome.html", "welcome.js", "engine_worker.js", "LICENSE",
         "carcassonne_engine.py", "neural_evaluator.py", "torch_free.py", "browser_coach.py",
         "carcassonne_model.pt"]
DIRS = ["images", "pyodide"]
# Images de travail du livre, non utilisées par l'extension (le paquet reste léger)
EXCLURE = {"images/livre_recto_verso.jpg", "images/livre_recto_verso_en.jpg"}
REQUIRED = ["pyodide/python_stdlib.zip", "pyodide/pyodide.asm.wasm", "pyodide/pyodide.js",
            "pyodide/pyodide.asm.js", "pyodide/pyodide-lock.json", "carcassonne_model.pt"]

version = json.load(open("manifest.json", encoding="utf-8"))["version"]
out = f"carcassonne-coach-{version}.xpi"
names = list(FILES)
for d in DIRS:
    for root, _, files in os.walk(d):
        names += [n for n in (os.path.join(root, f).replace(os.sep, "/") for f in sorted(files))
                  if n not in EXCLURE]
missing = [n for n in names + REQUIRED if not os.path.exists(n)]
if missing:
    sys.exit(f"❌ Fichiers manquants : {', '.join(sorted(set(missing)))}")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for n in names:
        z.write(n, n)
with zipfile.ZipFile(out) as z:
    inside = set(z.namelist())
assert all(r in inside for r in REQUIRED), "fichier indispensable absent du paquet"
print(f"✅ {out} : {len(inside)} fichiers, {os.path.getsize(out) / 1e6:.1f} Mo (python_stdlib.zip inclus)")
