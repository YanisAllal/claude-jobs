"""Génère une lettre de motivation PDF à partir de lettre.md.

Mise en page : Times 12 pt, coordonnées en haut à gauche (e-mail en lien bleu souligné), lieu et date
alignés à droite, « Objet : » en gras, formule d'appel et paragraphes avec retrait de première ligne, formule
finale sans retrait, signature alignée à droite.

Format du fichier lettre.md :
    Objet : Candidature au poste de ...

    Madame, Monsieur,

    Premier paragraphe...

    Paragraphe suivant...

    Formule finale (dernier paragraphe, sans retrait).

Lettre en anglais : commencer par « Subject: ... » au lieu de « Objet : ... » (date, objet et téléphone en anglais).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]

POLICE, GRAS, TAILLE, INTERLIGNE = "Times-Roman", "Times-Bold", 12, 14.5
RETRAIT = 1.25 * cm

base = ParagraphStyle("base", fontName=POLICE, fontSize=TAILLE, leading=INTERLIGNE, alignment=TA_LEFT)
droite = ParagraphStyle("droite", parent=base, alignment=TA_RIGHT)
objet = ParagraphStyle("objet", parent=base, fontName=GRAS)
corps = ParagraphStyle("corps", parent=base, firstLineIndent=RETRAIT, spaceAfter=INTERLIGNE)
final = ParagraphStyle("final", parent=base, spaceAfter=INTERLIGNE)


def date_fr(d: date) -> str:
    return f"{d.day} {MOIS[d.month - 1]} {d.year}" if d.day != 1 else f"1er {MOIS[d.month - 1]} {d.year}"


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def date_en(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def lire_lettre(chemin: Path) -> tuple[str, list[str], str]:
    """Renvoie (objet, paragraphes, langue) ; langue = "en" si la lettre commence par « Subject: »."""
    blocs = [b.strip() for b in chemin.read_text(encoding="utf-8").split("\n\n") if b.strip()]
    titre, langue = "", "fr"
    if blocs and blocs[0].lower().startswith(("objet", "subject")):
        langue = "en" if blocs[0].lower().startswith("subject") else "fr"
        titre = blocs.pop(0).split(":", 1)[1].strip()
    # un paragraphe = un bloc ; les retours à la ligne internes sont des espaces ; apostrophe typographique comme le modèle
    return titre.replace("'", "’"), [" ".join(b.split()).replace("'", "’") for b in blocs], langue


def retirer_signature(paragraphes: list[str], nom: str) -> list[str]:
    """La mise en page signe déjà à droite : retire un dernier bloc qui n'est que le nom (« Camille Martin », « Camille »…)."""
    mots = {m.lower() for m in nom.split()}
    while paragraphes and paragraphes[-1].strip(" .,").lower().split() and \
            set(paragraphes[-1].strip(" .,").lower().split()) <= mots:
        paragraphes = paragraphes[:-1]
    return paragraphes


def generer(source: Path, sortie: Path, profil: dict, ville: str = "Paris", jour: date | None = None) -> Path:
    titre, paragraphes, langue = lire_lettre(source)
    paragraphes = retirer_signature(paragraphes, profil["nom"])
    en = langue == "en"
    if len(paragraphes) < 3:
        raise ValueError(f"{source} : il faut une formule d'appel, au moins un paragraphe et une formule finale.")
    nom = profil["nom"].split()
    nom_affiche = " ".join(nom[:-1] + [nom[-1].upper()])
    email = str(profil.get("email") or "")

    elems = [
        Paragraph(escape(nom_affiche), base),
        *([Paragraph(escape(profil["adresse"]), base)] if profil.get("adresse") else []),
        *([Paragraph(f'<link href="mailto:{escape(email)}" color="#1155cc"><u>{escape(email)}</u></link>', base)] if email else []),
        *([Paragraph(f"{'Phone:' if en else 'Tél. :'} {escape(str(profil['telephone']))}", base)] if profil.get("telephone") else []),
        *([Paragraph(escape(str(profil["linkedin"])), base)] if profil.get("linkedin") else []),
        Spacer(1, INTERLIGNE * 1.5),
        Paragraph(f"{escape(ville)}, {date_en(jour or date.today())}" if en
                  else f"{escape(ville)}, le {date_fr(jour or date.today())}", droite),
        Spacer(1, INTERLIGNE * 1.5),
    ]
    if titre:
        elems += [Paragraph(f"{'Subject:' if en else 'Objet :'} {escape(titre)}", objet), Spacer(1, INTERLIGNE * 2)]
    appel, *milieu, formule = paragraphes
    elems.append(Paragraph(escape(appel), corps))
    elems += [Paragraph(escape(p), corps) for p in milieu]
    elems += [Paragraph(escape(formule), final), Spacer(1, INTERLIGNE * 0.5), Paragraph(escape(nom_affiche), droite)]

    doc = SimpleDocTemplate(str(sortie), pagesize=A4, leftMargin=2.5 * cm, rightMargin=2.5 * cm,
                            topMargin=2.5 * cm, bottomMargin=2 * cm,
                            title=f"{'Cover letter' if en else 'Lettre de motivation'} — {titre}", author=nom_affiche)
    doc.build(elems)
    return sortie
