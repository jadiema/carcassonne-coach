"""
🔒 carcassonne-coach — aucun pseudo de joueur dans le dépôt
==========================================================
À lancer juste avant de rendre le dépôt public :

    git fetch --tags                 # examiner aussi les étiquettes créées sur GitHub
    python verifier_pseudos.py

Les pseudos sont lus AU MOMENT DE L'EXÉCUTION dans les parties de parties/
(dossier ignoré par git) : ce fichier n'en contient aucun. Sont exclus :
  - l'auteur du dépôt (git config user.name) et les noms passés par --exclure ;
  - la liste blanche versionnée pseudos_autorises.txt : personnes qui ont accepté
    d'être nommées (un pseudo par ligne, # pour un commentaire) ;
  - les noms d'auto-jeu : ceux qui n'apparaissent que dans les parties
    d'auto-jeu (sous-dossiers selfplay*, fichiers sp_*.json).

Recherche en sous-chaîne, sans tenir compte de la casse, dans :
  1. les fichiers suivis (et les nouveaux fichiers non ignorés, qui seraient commités) ;
  2. tout l'historique : contenus et chemins de fichiers de tous les commits
     de toutes les branches et étiquettes, messages de commits et d'étiquettes.

Affiche le fichier, le commit et le pseudo trouvés. Code de sortie : 0 si rien
n'est trouvé, 1 s'il y a au moins un pseudo, 2 si la vérification est impossible
(aucun pseudo lu dans parties/).

Options pour le garde-fou avant chaque push (hook pre-push, voir le README) :
  --rapide          ne lit pas les parties d'auto-jeu (leurs noms ne sont jamais
                    cherchés : seul le compte des noms d'auto-jeu exclus disparaît) ;
  --commits REV...  n'examine que ce qui partirait : objets, chemins, messages de
                    commits et d'étiquettes atteignables depuis REV (syntaxe de
                    git rev-list, par exemple  <sha> --not --remotes=origin),
                    sans le dossier de travail ni le reste de l'historique.
  --installer-hook  installe ce garde-fou dans .git/hooks/pre-push (local, non versionné) :
                    chaque git push est alors bloqué si un pseudo part.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TAILLE_MAX = 20_000_000          # au-delà (modèles, archives), le fichier n'est pas lu
LISTE_BLANCHE = ROOT / "pseudos_autorises.txt"


def lire_liste_blanche(chemin: Path = LISTE_BLANCHE) -> set:
    """Pseudos autorisés (en minuscules) ; ensemble vide si le fichier n'existe pas."""
    try:
        lignes = chemin.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {l.strip().lower() for l in lignes if l.strip() and not l.strip().startswith("#")}


MARQUE_HOOK = "# carcassonne-coach : garde-fou verifier_pseudos.py"
HOOK = f"""#!/bin/sh
{MARQUE_HOOK}
# Installé par « python verifier_pseudos.py --installer-hook ».
# Bloque le push si un pseudo de joueur se trouve dans ce qui part
# (fichiers, chemins, messages de commits et d'étiquettes absents du dépôt distant).
remote="$1"
zero=0000000000000000000000000000000000000000
revs=""
while read lref lsha rref rsha; do
    [ "$lsha" = "$zero" ] && continue        # suppression d'une branche ou d'une étiquette
    revs="$revs $lsha"
done
[ -z "$revs" ] && exit 0
cd "$(git rev-parse --show-toplevel)" || exit 1
if git remote | grep -qx "$remote"; then deja="--remotes=$remote"; else deja="--remotes"; fi
python verifier_pseudos.py --commits $revs --not $deja
code=$?
if [ $code -ne 0 ]; then
    echo "⛔ push bloqué par verifier_pseudos.py (code $code)." >&2
    exit 1
fi
exit 0
"""


def installer_hook() -> int:
    cible = Path(git("rev-parse", "--git-path", "hooks/pre-push").strip())
    if not cible.is_absolute():
        cible = ROOT / cible
    if cible.exists() and MARQUE_HOOK not in cible.read_text(encoding="utf-8", errors="replace"):
        print(f"❌ {cible} existe déjà et n'a pas été installé par ce script : rien n'est modifié.")
        return 2
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(HOOK, encoding="utf-8", newline="\n")
    try:
        cible.chmod(0o755)
    except OSError:
        pass
    print(f"✅ Garde-fou installé : {cible}")
    return 0


def git(*args, binary=False, stdin=None):
    r = subprocess.run(["git", *args], cwd=ROOT, input=stdin, capture_output=True)
    if r.returncode != 0:
        sys.exit(f"❌ git {' '.join(args)} : {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def is_selfplay(path: Path, parties: Path) -> bool:
    rel = path.relative_to(parties).parts
    return path.name.startswith("sp_") or any(p.lower().startswith("selfplay") for p in rel[:-1])


def lire_pseudos(parties: Path, exclus: set, rapide: bool = False) -> tuple:
    humains, autojeu, lus = set(), set(), 0
    for f in parties.rglob("*.json"):
        if rapide and is_selfplay(f, parties):
            continue                    # noms d'auto-jeu : jamais cherchés de toute façon
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        noms = {str(p.get("name", "")).strip() for p in data.get("players", []) if isinstance(p, dict)}
        noms.discard("")
        (autojeu if is_selfplay(f, parties) else humains).update(noms)
        lus += 1
    pseudos = {n for n in humains if n.lower() not in exclus}
    return pseudos, lus, len(autojeu - humains)


def est_binaire(b: bytes) -> bool:
    return b"\0" in b[:8192]


def main():
    # Sortie redirigée (hook git, tube) : ne pas planter sur ✅/❌ sous Windows (cp1252)
    for flux in (sys.stdout, sys.stderr):
        try:
            if flux.isatty():
                flux.reconfigure(errors="replace")
            else:                       # lu par git / Git Bash, qui affichent l'UTF-8
                flux.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Vérifie qu'aucun pseudo de joueur n'est dans le dépôt ni son historique.")
    ap.add_argument("--parties", default=str(ROOT / "parties"), help="dossier des parties (défaut : parties/)")
    ap.add_argument("--exclure", action="append", default=[], help="nom à ne pas chercher (répétable)")
    ap.add_argument("--min", type=int, default=4,
                    help="longueur minimale d'un pseudo cherché (défaut 4 : les noms plus courts "
                         "donneraient des faux positifs partout ; --min 1 pour tout chercher)")
    ap.add_argument("--rapide", action="store_true",
                    help="ne pas lire les parties d'auto-jeu (même liste de pseudos, beaucoup plus rapide)")
    ap.add_argument("--commits", nargs=argparse.REMAINDER, default=None, metavar="REV",
                    help="n'examiner que les objets et messages atteignables depuis REV "
                         "(arguments de git rev-list ; à placer en dernier)")
    ap.add_argument("--installer-hook", action="store_true",
                    help="installer le garde-fou dans .git/hooks/pre-push")
    a = ap.parse_args()
    if a.installer_hook:
        return installer_hook()

    auteur = git("config", "user.name").strip()
    autorises = lire_liste_blanche()
    exclus = {x.lower() for x in a.exclure + ([auteur] if auteur else [])} | autorises
    pseudos, lus, n_autojeu = lire_pseudos(Path(a.parties), exclus, a.rapide or a.commits is not None)
    courts = {p for p in pseudos if len(p) < a.min}
    pseudos -= courts
    print(f"Parties lues : {lus} · pseudos cherchés : {len(pseudos)} "
          f"(exclus : auteur du dépôt, {len(autorises)} pseudo(s) autorisé(s) (pseudos_autorises.txt), "
          + ("noms d'auto-jeu" if a.rapide or a.commits is not None else f"{n_autojeu} nom(s) d'auto-jeu")
          + (f", {len(courts)} pseudo(s) de moins de {a.min} caractères" if courts else "") + ")")
    if not pseudos:
        print("❌ Aucun pseudo lu : vérification impossible (dossier parties/ vide ou absent ?)")
        return 2

    motif = re.compile("|".join(re.escape(p) for p in sorted(pseudos, key=len, reverse=True)), re.IGNORECASE)
    canon = {p.lower(): p for p in pseudos}

    def trouves(texte: str) -> set:
        return {canon.get(m.group(0).lower(), m.group(0)) for m in motif.finditer(texte)}

    resultats = []      # (où, fichier, commit, pseudo)

    # 1. Fichiers actuels qui seraient commités (pas en mode --commits : seul ce qui part compte)
    revs = ["--all"] if a.commits is None else a.commits
    fichiers = [] if a.commits is not None else \
        [f for f in git("ls-files", "-co", "--exclude-standard", "-z").split("\0") if f]
    for f in fichiers:
        p = ROOT / f
        for n in trouves(f):
            resultats.append(("actuel", f, "(dossier de travail)", n))
        try:
            if not p.is_file() or p.stat().st_size > TAILLE_MAX:
                continue
            b = p.read_bytes()
        except OSError:
            continue
        if not est_binaire(b):
            for n in trouves(b.decode("utf-8", "replace")):
                resultats.append(("actuel", f, "(dossier de travail)", n))

    # 2. Historique : tous les objets de toutes les références (branches, étiquettes, distantes),
    #    ou seulement ceux qui partent (--commits)
    objets = git("rev-list", "--objects", *revs).splitlines() if revs else []
    chemins, tous = {}, set()
    for ligne in objets:
        sha, _, chemin = ligne.partition(" ")
        tous.add(sha)
        if chemin:
            chemins.setdefault(sha, set()).add(chemin)
    # chemins de fichiers
    for sha, cs in chemins.items():
        for c in cs:
            for n in trouves(c):
                resultats.append(("historique", c, None, n))
    # contenus : lecture groupée des objets « blob »
    info = git("cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
               stdin="\n".join(chemins).encode()).splitlines() if chemins else []
    blobs = [l.split()[0] for l in info if len(l.split()) == 3 and l.split()[1] == "blob"
             and int(l.split()[2]) <= TAILLE_MAX]
    if blobs:
        brut = git("cat-file", "--batch", binary=True, stdin="\n".join(blobs).encode())
        i = 0
        while i < len(brut):
            fin = brut.index(b"\n", i)
            sha, _, taille = brut[i:fin].decode().split()
            debut = fin + 1
            contenu = brut[debut:debut + int(taille)]
            i = debut + int(taille) + 1
            if est_binaire(contenu):
                continue
            ns = trouves(contenu.decode("utf-8", "replace"))
            for c in sorted(chemins.get(sha, ())):
                for n in ns:
                    resultats.append(("historique", c, sha, n))
    # messages de commits et d'étiquettes
    for bloc in (git("log", "--format=%h%x00%B%x01", *revs).split("\x01") if revs else []):
        if "\0" in bloc:
            h, msg = bloc.strip("\n").split("\0", 1)
            for n in trouves(msg):
                resultats.append(("historique", "(message de commit)", h, n))
    if a.commits is None:
        for bloc in git("for-each-ref", "refs/tags", "--format=%(refname:short)%00%(contents)%01").split("\x01"):
            if "\0" in bloc:
                t, msg = bloc.strip("\n").split("\0", 1)
                for n in trouves(t + "\n" + msg):
                    resultats.append(("historique", f"(étiquette {t})", t, n))
    elif tous:
        # étiquettes annotées qui partent : objets de type « tag » parmi les objets examinés
        types = git("cat-file", "--batch-check=%(objectname) %(objecttype)",
                    stdin="\n".join(tous).encode()).splitlines()
        for l in types:
            sha, _, typ = l.partition(" ")
            if typ == "tag":
                for n in trouves(git("cat-file", "tag", sha)):
                    resultats.append(("historique", "(étiquette)", sha[:7], n))

    # Commits qui contiennent chaque contenu fautif (ceux qui l'ont ajouté ou retiré)
    commits_de = {}
    def commits(sha):
        if sha not in commits_de:
            commits_de[sha] = git("log", "--format=%h", f"--find-object={sha}", *revs).split() or ["?"]
        return commits_de[sha]

    vus, lignes = set(), []
    for ou, fichier, ref, n in resultats:
        if ou == "historique" and ref is None:
            ref = "(chemin de fichier)"
        elif ou == "historique" and re.fullmatch(r"[0-9a-f]{40}", ref or ""):
            ref = ", ".join(commits(ref))
        cle = (ou, fichier, ref, n)
        if cle not in vus:
            vus.add(cle)
            lignes.append(cle)

    if not lignes:
        print("✅ Aucun pseudo trouvé dans ce qui part." if a.commits is not None else
              "✅ Aucun pseudo trouvé dans les fichiers suivis ni dans l'historique.")
        return 0
    lignes.sort()
    print(f"\n❌ {len(lignes)} occurrence(s) :")
    for ou, fichier, ref, n in lignes:
        print(f"  [{ou}] {fichier} · commit {ref} · pseudo « {n} »")
    if a.commits is not None:
        print("\nRetirer le pseudo des commits qui ne sont pas encore poussés "
              "(git commit --amend, ou git rebase pour un commit plus ancien), puis relancer git push.")
    else:
        print("\nFichiers actuels : à corriger avant le commit. Historique : à réécrire "
              "(git filter-repo) avant de rendre le dépôt public.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
