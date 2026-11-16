"""Génère cv.pdf depuis le cv.md d'un dossier, sans LaTeX (reportlab, déjà installé par ./installer.sh).

Même format de cv.md que cv_pdf.py (voir sa docstring) : nom, accroche, coordonnées, sections « ## », entrées
« **Entreprise — Intitulé** · Lieu · dates » suivies de puces, formation « - **École** — Diplôme · dates ».
Mise en page : Helvetica, nom centré, titres de section en couleur soulignés d'un filet, dates alignées à droite.
Si le CV dépasse une page, la police et les marges sont réduites, comme pour la version LaTeX.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from cv_pdf import entete, joindre

COULEUR = "1F3A5F"


def en_ligne(t: str) -> str:
    """Markdown en ligne → balises reportlab : **gras**, *italique*, `code`, [texte](lien)."""
    morceaux = re.split(r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|(?<![\w*])\*[^*\s][^*]*?\*(?![\w*]))", t)
    sortie = []
    for m in morceaux:
        if not m:
            continue
        if m.startswith("**") and m.endswith("**") and len(m) > 4:
            sortie.append("<b>" + en_ligne(m[2:-2]) + "</b>")
        elif m.startswith("`"):
            sortie.append('<font face="Courier">' + escape(m[1:-1]) + "</font>")
        elif m.startswith("[") and "](" in m:
            texte, url = m[1:-1].split("](", 1)
            sortie.append(f'<link href="{escape(url)}">{escape(texte)}</link>')
        elif m.startswith("*") and m.endswith("*") and len(m) > 2:
            sortie.append("<i>" + en_ligne(m[1:-1]) + "</i>")
        else:
            sortie.append(escape(m))
    return "".join(sortie)


def styles(taille: float, couleur: str) -> dict:
    accent = colors.HexColor("#" + couleur)
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=taille, leading=taille * 1.28)
    return {
        "accent": accent,
        "base": base,
        "nom": ParagraphStyle("nom", parent=base, fontName="Helvetica-Bold", fontSize=taille * 2, leading=taille * 2.3,
                              alignment=TA_CENTER, textColor=accent),
        "accroche": ParagraphStyle("accroche", parent=base, fontName="Helvetica-Oblique", alignment=TA_CENTER),
        "contact": ParagraphStyle("contact", parent=base, fontSize=taille * 0.92, alignment=TA_CENTER),
        "section": ParagraphStyle("section", parent=base, fontName="Helvetica-Bold", fontSize=taille * 1.08,
                                  textColor=accent, spaceBefore=taille * 0.7, spaceAfter=1),
        "titre": ParagraphStyle("titre", parent=base, fontName="Helvetica-Bold"),
        "date": ParagraphStyle("date", parent=base, alignment=TA_RIGHT),
        "puce": ParagraphStyle("puce", parent=base, leftIndent=11, bulletIndent=2),
        "sous_puce": ParagraphStyle("sous_puce", parent=base, leftIndent=22, bulletIndent=12),
        "detail": ParagraphStyle("detail", parent=base, fontSize=taille * 0.9, leading=taille * 1.15, leftIndent=11,
                                 textColor=colors.HexColor("#333333")),
    }


def entree(ligne: str, formation: bool, st: dict, largeur: float) -> list | None:
    """« **A — B** · lieu · dates » → titre en gras, puis sous-titre à gauche et dates à droite."""
    e = entete(ligne)
    if not e:
        return None
    gras, tete, avant, date, apres = e
    a, _, b = gras.partition(" — ")
    if formation:
        titre, sous = (a, b) if b else (gras, "")
    else:
        titre, sous = (b, a) if b else (gras, "")
    sous = joindre([sous, tete, *avant])
    tableau = Table([[Paragraph(en_ligne(titre), st["titre"]), ""],
                     [Paragraph(en_ligne(sous), st["base"]), Paragraph(en_ligne(date), st["date"])]],
                    colWidths=[largeur - 4.2 * cm, 4.2 * cm])
    tableau.setStyle(TableStyle([("SPAN", (0, 0), (1, 0)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                 ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    elems = [Spacer(1, 2), tableau]
    if apres:
        elems.append(Paragraph("<i>" + en_ligne(" · ".join(apres)) + "</i>", st["base"]))
    return elems


def construire(md: str, st: dict, largeur: float) -> list:
    lignes = md.replace("\r", "").split("\n")
    elems: list = []
    i = 0
    nom, accroche, contact, resume = "", "", "", []
    while i < len(lignes) and not lignes[i].startswith("## "):
        l = lignes[i].strip()
        if l.startswith("# "):
            nom = l[2:].strip()
        elif l.startswith("**") and l.endswith("**") and not accroche and not resume:
            accroche = l[2:-2]
        elif ("@" in l or re.search(r"\+?\d[\d ]{8,}", l)) and not contact:
            contact = l
        elif l and l != "---":
            resume.append(l)
        i += 1
    elems.append(Paragraph(escape(nom or "CV"), st["nom"]))
    if accroche:
        elems.append(Paragraph(en_ligne(accroche), st["accroche"]))
    if contact:
        elems.append(Paragraph("   ·   ".join(en_ligne(p.strip()) for p in contact.split(" · ")), st["contact"]))
    elems += [Spacer(1, 3), HRFlowable(width="100%", thickness=1.2, color=st["accent"], spaceAfter=3)]
    if resume:
        elems.append(Paragraph(en_ligne(" ".join(resume)), st["base"]))

    dans_entree = False
    for brut in lignes[i:]:
        if not brut.strip() or brut.strip() == "---":
            continue
        if brut.startswith("## "):
            elems += [Paragraph(en_ligne(brut[3:].strip()).upper(), st["section"]),
                      HRFlowable(width="100%", thickness=0.5, color=st["accent"], spaceBefore=0, spaceAfter=2)]
            dans_entree = False
            continue
        retrait = len(brut) - len(brut.lstrip())
        l = brut.strip()
        if retrait >= 2 and not l.startswith(("- ", "* ")):
            elems.append(Paragraph(en_ligne(l), st["detail"]))
            continue
        if l.startswith(("- ", "* ")):
            texte = l[2:].strip()
            rendu = entree(texte, True, st, largeur)
            if rendu:
                elems.append(KeepTogether(rendu))
                dans_entree = False
            else:
                style = st["sous_puce"] if dans_entree else st["puce"]
                elems.append(Paragraph(en_ligne(texte), style, bulletText="–" if dans_entree else "•"))
            continue
        rendu = entree(l, False, st, largeur)
        if rendu:
            elems.append(KeepTogether(rendu))
            dans_entree = True
            continue
        dans_entree = False
        elems.append(Paragraph(en_ligne(l), st["base"]))
    return elems


ESSAIS = [  # (taille de police, marge latérale, marge haute) du plus aéré au plus serré
    (10.5, 1.9, 1.3), (10, 1.6, 1.1), (9.5, 1.5, 1.0), (9, 1.3, 0.8),
]


def generer(source: Path, sortie: Path, couleur: str = COULEUR) -> tuple[Path, int]:
    """Construit sortie (cv.pdf) depuis source (cv.md). Renvoie (chemin, nombre de pages)."""
    md = source.read_text(encoding="utf-8")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", couleur or ""):
        couleur = COULEUR
    nom = next((l[2:].strip() for l in md.splitlines() if l.startswith("# ")), "CV")
    pages, contenu = 0, b""
    for taille, cote, haut in ESSAIS:
        tampon = io.BytesIO()
        doc = SimpleDocTemplate(tampon, pagesize=A4, leftMargin=cote * cm, rightMargin=cote * cm,
                                topMargin=haut * cm, bottomMargin=haut * cm, title=f"{nom} - CV", author=nom)
        doc.build(construire(md, styles(taille, couleur), A4[0] - 2 * cote * cm))
        pages, contenu = doc.page, tampon.getvalue()
        if pages <= 1:
            break
    sortie.write_bytes(contenu)
    return sortie, pages
