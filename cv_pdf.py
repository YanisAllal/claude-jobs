"""Génère cv.pdf depuis le cv.md d'un dossier, avec une mise en page LaTeX classique : Latin Modern, nom centré,
accroche, filet épais, titres de section soulignés, puces, dates alignées à droite, couleur d'accent discrète.
Nécessite pdflatex (MacTeX / BasicTeX sur macOS, texlive sur Linux). Sans LaTeX, voir cv_pdf_simple.py.

Format attendu de cv.md (celui des dossiers, le même pour les deux mises en page) :
    # Prénom Nom
    **Accroche**
    +33 … · e-mail · Paris
    Paragraphe de résumé (facultatif).
    ## Section
    **Entreprise — Intitulé** · Lieu · dates          ← expérience (suivie de puces « - … »)
    - **École** — Diplôme · dates · mention           ← formation
      ligne en retrait = détail de la puce au-dessus (cours…)
    - **Projet** (Python, 2025) : description         ← puce simple
    **Compétences** : …                               ← ligne simple

Compilation : pdflatex. Si le CV dépasse une page, la mise en page est resserrée, puis la police réduite.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

COULEUR = "1F3A5F"  # bleu nuit par défaut ; réglable dans preferences.yml → cv.couleur (000000 = noir)

ANNEE = re.compile(r"(19|20)\d\d")
MOIS = re.compile(r"\b(janv|févr|mars|avr|mai|juin|juil|août|sept|oct|nov|déc|jan|feb|mar|apr|may|jun|jul|aug|sep|dec)", re.I)

REMPLACEMENTS = {
    " ": "~", " ": "\\,", " ": "\\,",
    "→": "$\\rightarrow$", "←": "$\\leftarrow$", "≥": "$\\geq$", "≤": "$\\leq$", "×": "$\\times$", "±": "$\\pm$",
    "≈": "$\\approx$", "€": "\\texteuro{}", "•": "\\textbullet{}", "✓": "", "★": "",
}


def echapper(t: str) -> str:
    t = t.replace("\\", "\\textbackslash{}")
    for a, b in (("&", "\\&"), ("%", "\\%"), ("$", "\\$"), ("#", "\\#"), ("_", "\\_"), ("{", "\\{"), ("}", "\\}"),
                 ("~", "\\textasciitilde{}"), ("^", "\\textasciicircum{}")):
        t = t.replace(a, b)
    t = t.replace("\\textbackslash\\{\\}", "\\textbackslash{}")
    for a, b in REMPLACEMENTS.items():
        t = t.replace(a, b)
    return t


def en_ligne(t: str) -> str:
    """Markdown en ligne → LaTeX : **gras**, *italique*, `code`, [texte](lien), e-mails."""
    morceaux = re.split(r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|(?<![\w*])\*[^*\s][^*]*?\*(?![\w*]))", t)
    sortie = []
    for m in morceaux:
        if not m:
            continue
        if m.startswith("**") and m.endswith("**") and len(m) > 4:
            sortie.append("\\textbf{" + en_ligne(m[2:-2]) + "}")
        elif m.startswith("`"):
            sortie.append("\\texttt{" + echapper(m[1:-1]) + "}")
        elif m.startswith("[") and "](" in m:
            texte, url = m[1:-1].split("](", 1)
            sortie.append("\\href{" + url.replace("%", "\\%").replace("#", "\\#") + "}{" + echapper(texte) + "}")
        elif m.startswith("*") and m.endswith("*") and len(m) > 2:
            sortie.append("\\textit{" + en_ligne(m[1:-1]) + "}")
        else:
            e = echapper(m)
            e = re.sub(r"([\w.+-]+@[\w-]+(\.[\w-]+)+)", lambda x: "\\href{mailto:" + x.group(1) + "}{\\texttt{" + x.group(1) + "}}", e)
            sortie.append(e)
    return "".join(sortie)


def est_date(p: str) -> bool:
    return bool(ANNEE.search(p)) and len(p) < 45 and (bool(MOIS.search(p)) or bool(re.fullmatch(r"[\s\d–\-—/().a-zA-Zéû]+", p)))


def entete(ligne: str):
    """Ligne d'entrée « **A — B** reste · … · dates · … » → (gauche_gras, sous_titre, date, extra) ou None."""
    m = re.match(r"^\*\*(.+?)\*\*(.*)$", ligne)
    if not m or " · " not in ligne:
        return None
    gras, reste = m.group(1).strip(), m.group(2)
    parties = [p.strip() for p in reste.split(" · ")]
    tete = parties[0].lstrip("—–- ").strip()
    autres = parties[1:]
    i_date = next((i for i, p in enumerate(autres) if est_date(p)), None)
    if i_date is None:
        return None
    return gras, tete, autres[:i_date], autres[i_date], autres[i_date + 1:]


def joindre(morceaux: list[str]) -> str:
    """Joint par des virgules, sauf devant une parenthèse : « Licence (option …) »."""
    texte = ""
    for m in (x for x in morceaux if x):
        texte += (" " if m.startswith("(") else ", ") + m if texte else m
    return texte


def rendre_entree(ligne: str, puce: bool) -> str | None:
    e = entete(ligne)
    if not e:
        return None
    gras, tete, avant, date, apres = e
    a, _, b = gras.partition(" — ")
    if puce:  # formation : école en gras, puis diplôme \hfill dates
        titre, sous = (a, b) if b else (gras, "")
        sous = joindre([sous, tete, *avant])
    else:     # expérience : intitulé en gras, puis entreprise et lieu \hfill dates
        titre, sous = (b, a) if b else (gras, "")
        sous = joindre([sous, tete, *avant])
    l2 = en_ligne(sous) + " \\hfill " + en_ligne(date)
    if apres:
        l2 += "\\\\[1pt] \\textit{" + en_ligne(" · ".join(apres)) + "}"
    return "\\textbf{" + en_ligne(titre) + "}\\\\ " + l2


def corps(md: str) -> tuple[dict, str]:
    lignes = md.replace("\r", "").split("\n")
    tete = {"nom": "", "accroche": "", "contact": "", "resume": []}
    i = 0
    while i < len(lignes) and not lignes[i].startswith("## "):
        l = lignes[i].strip()
        if l.startswith("# "):
            tete["nom"] = l[2:].strip()
        elif l.startswith("**") and l.endswith("**") and not tete["accroche"] and not tete["resume"]:
            tete["accroche"] = l[2:-2]
        elif ("@" in l or re.search(r"\+?\d[\d ]{8,}", l)) and not tete["contact"]:
            tete["contact"] = l
        elif l and l != "---":
            tete["resume"].append(l)
        i += 1

    out: list[str] = []
    liste = False      # itemize de premier niveau ouvert
    sous = False       # sous-liste (missions) ouverte
    entree_ouverte = False

    def fermer_sous():
        nonlocal sous
        if sous:
            out.append("\\end{itemize}")
            sous = False

    def fermer_liste():
        nonlocal liste, entree_ouverte
        fermer_sous()
        if liste:
            out.append("\\end{itemize}")
            liste = False
        entree_ouverte = False

    def ouvrir_liste():
        nonlocal liste
        if not liste:
            out.append("\\begin{itemize}")
            liste = True

    for brut in lignes[i:]:
        if not brut.strip() or brut.strip() == "---":
            continue
        if brut.startswith("## "):
            fermer_liste()
            out.append("\\section*{" + en_ligne(brut[3:].strip()) + "}")
            continue
        retrait = len(brut) - len(brut.lstrip())
        l = brut.strip()
        if retrait >= 2 and not l.startswith("- ") and out:   # détail de la puce précédente
            if out[-1].endswith("%detail"):   # suite du même détail : même paragraphe
                out[-1] = out[-1][:-len("}%detail")] + " " + en_ligne(l) + "}%detail"
            else:
                out[-1] += "\\\\[1pt] {\\small " + en_ligne(l) + "}%detail"
            continue
        if l.startswith("- ") or l.startswith("* "):
            texte = l[2:].strip()
            if entree_ouverte and not (rendu := rendre_entree(texte, True)):
                if not sous:
                    out.append("\\begin{itemize}[label=\\textendash, leftmargin=14pt, itemsep=0pt, topsep=1pt]")
                    sous = True
                out.append("\\item " + en_ligne(texte))
                continue
            fermer_sous()
            ouvrir_liste()
            rendu = rendre_entree(texte, True)
            entree_ouverte = False
            out.append("\\item " + (rendu or en_ligne(texte)))
            continue
        rendu = rendre_entree(l, False)
        if rendu:
            fermer_sous()
            ouvrir_liste()
            out.append("\\item " + rendu)
            entree_ouverte = True
            continue
        fermer_liste()
        out.append(en_ligne(l) + "\\\\")
    fermer_liste()
    # « \\ » final avant un titre de section ou en fin de texte : inutile
    texte = "\n".join(out)
    texte = re.sub(r"\\\\\n(\\section\*)", r"\n\1", texte)
    texte = re.sub(r"\\\\$", "", texte)
    return tete, texte


def document(md: str, taille: str, marges: str, interligne: str, couleur: str = COULEUR) -> str:
    tete, texte = corps(md)
    contact = " \\quad ".join(en_ligne(p.strip()) for p in tete["contact"].split(" · ")) if tete["contact"] else ""
    resume = en_ligne(" ".join(tete["resume"])) if tete["resume"] else ""
    anglais = bool(re.search(r"^## (Experience|Education|Skills|Projects)", md, re.M))
    langue = "english" if anglais else "french"
    listes_fr = "" if anglais else r"\frenchsetup{StandardLists=true}"
    accroche = (r"{\itshape " + en_ligne(tete["accroche"]) + r"}\\[3pt]") if tete["accroche"] else ""
    bloc_resume = (r"\vspace{2pt}" + "\n" + resume + r"\par") if resume else ""
    nom = echapper(tete["nom"] or "CV")
    return rf"""\documentclass[{taille}]{{article}}
\input{{glyphtounicode}}
\pdfgentounicode=1
\usepackage[T1]{{fontenc}}
\usepackage[utf8]{{inputenc}}
\usepackage{{lmodern}}
\usepackage{{textcomp}}
\usepackage[{langue}]{{babel}}
\usepackage[a4paper,{marges}]{{geometry}}
\usepackage[dvipsnames]{{xcolor}}
\definecolor{{accent}}{{HTML}}{{{couleur}}}
\usepackage{{enumitem}}
\usepackage{{titlesec}}
\usepackage[hidelinks,pdftitle={{{nom} - CV}},pdfauthor={{{nom}}}]{{hyperref}}
\pagestyle{{empty}}
\setlength{{\parindent}}{{0pt}}
\linespread{{{interligne}}}
\titleformat{{\section}}{{\color{{accent}}\normalsize\bfseries\scshape}}{{}}{{0pt}}{{}}[\vspace{{-7pt}}{{\color{{accent}}\rule{{\linewidth}}{{0.5pt}}}}]
\titlespacing*{{\section}}{{0pt}}{{6pt}}{{4pt}}
\setlist[itemize]{{leftmargin=12pt,itemsep=2pt,topsep=1pt,label=\textbullet}}
{listes_fr}
\begin{{document}}
\begin{{center}}
  {{\color{{accent}}\LARGE\bfseries {nom}}}\\[3pt]
  {accroche}
  {{\small {contact}}}
\end{{center}}
\vspace{{-6pt}}
{{\color{{accent}}\rule{{\linewidth}}{{1.2pt}}}}
{bloc_resume}
{texte}
\end{{document}}
"""


ESSAIS = [  # (taille, marges, interligne) du plus aéré au plus serré
    ("11pt", "top=1.2cm,bottom=1.0cm,left=1.9cm,right=1.9cm", "1.0"),
    ("11pt", "top=1.0cm,bottom=0.8cm,left=1.5cm,right=1.5cm", "0.97"),
    ("10pt", "top=1.0cm,bottom=0.8cm,left=1.5cm,right=1.5cm", "1.0"),
    ("10pt", "top=0.8cm,bottom=0.7cm,left=1.3cm,right=1.3cm", "0.95"),
]


def generer(source: Path, sortie: Path, couleur: str = COULEUR) -> tuple[Path, int]:
    """Compile source (cv.md) en sortie (cv.pdf). Renvoie (chemin, nombre de pages)."""
    md = source.read_text(encoding="utf-8")
    exe = shutil.which("pdflatex") or next((c for c in ("/Library/TeX/texbin/pdflatex", "/usr/bin/pdflatex") if Path(c).exists()), "")
    if not exe:
        raise RuntimeError("pdflatex introuvable (installer MacTeX/BasicTeX ou texlive).")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", couleur or ""):
        couleur = COULEUR
    pages = 0
    with tempfile.TemporaryDirectory() as tmp:
        for taille, marges, inter in ESSAIS:
            tex = Path(tmp) / "cv.tex"
            tex.write_text(document(md, taille, marges, inter, couleur), encoding="utf-8")
            r = subprocess.run([exe, "-interaction=nonstopmode", "-halt-on-error", "cv.tex"], cwd=tmp,
                               capture_output=True, text=True, encoding="latin-1")
            pdf = Path(tmp) / "cv.pdf"
            if r.returncode != 0 or not pdf.exists():
                erreurs = [l for l in r.stdout.splitlines() if l.startswith("!")][:3]
                raise RuntimeError(f"pdflatex a échoué pour {source} : {' | '.join(erreurs) or r.stdout[-400:]}")
            m = re.search(r"Output written on cv\.pdf \((\d+) page", r.stdout)
            pages = int(m.group(1)) if m else 1
            if pages <= 1:
                break
        shutil.copy(pdf, sortie)
        shutil.copy(tex, sortie.with_suffix(".tex"))
    return sortie, pages
