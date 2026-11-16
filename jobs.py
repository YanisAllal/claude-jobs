#!/usr/bin/env python3
"""claude-jobs : trouver des offres adaptées à ton CV et suivre tes candidatures.

Commandes :
  serveur    Tableau de bord dans le navigateur (profil, statuts, checklists, bouton « Préparer le dossier »)
  verifier   Vérifie l'installation et la configuration
  chercher   Recherche sur LinkedIn / Indeed / Glassdoor (avec garde-fous)
  ajouter    Ajoute une offre à la main
  noter      Enregistre le score et le résumé d'une offre (utilisé par Claude)
  statut     Change le statut d'une offre (postulee, entretien, refusee...)
  liste      Affiche les offres du suivi
  tableau    Régénère tableau_de_bord.html et les pages des offres
  lettre     Génère la lettre PDF d'un dossier
  cv         Génère le CV PDF d'un dossier
  lien       Enregistre le lien direct pour postuler (affiché sur la page de l'offre)
  demo       Ouvre le tableau de bord d'un profil fictif, pour découvrir l'outil

Les données personnelles (preferences.yml, cv.md, suivi.csv, data/, candidatures/, pages/) sont dans le dossier
du projet, ou dans celui de la variable d'environnement JOBS_DONNEES. Elles ne sont pas suivies par git.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
from contextlib import contextmanager
import hashlib
import json
import os
import random
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parent                              # code (modèles HTML, scripts)
DONNEES = Path(os.environ.get("JOBS_DONNEES") or RACINE).resolve()   # données personnelles
EXEMPLES = RACINE / "exemples"
PREFS = DONNEES / "preferences.yml"
CV_REFERENCE = DONNEES / "cv.md"
SUIVI = DONNEES / "suivi.csv"
DOSSIER_OFFRES = DONNEES / "data" / "offres"
ETAT = DONNEES / "data" / "etat.json"
CANDIDATURES = DONNEES / "candidatures"
TABLEAU = DONNEES / "tableau_de_bord.html"
PAGES = DONNEES / "pages"  # une page HTML par offre, régénérée avec le tableau
TACHES = DONNEES / "data" / "taches"  # dossiers préparés / complétés par Claude Code depuis le bouton de la page d'une offre
PORT = 8765

COLONNES = [
    "id", "date_ajout", "source", "titre", "entreprise", "lieu", "contrat",
    "teletravail", "salaire", "url", "score", "resume", "statut",
    "date_candidature", "date_maj", "prochaine_action", "notes",
    "lien_postuler", "canal",  # où et comment postuler, quand ce n'est pas l'url de l'offre (ex : candidature spontanée)
]

STATUTS = {
    "nouvelle": "Trouvée, pas encore analysée",
    "a_etudier": "Analysée, à regarder",
    "ecartee": "Ne convient pas / pas intéressé",
    "dossier_pret": "Dossier de candidature préparé",
    "postulee": "Candidature envoyée",
    "relancee": "Relance envoyée",
    "entretien": "Entretien prévu ou passé",
    "test": "Test technique / étude de cas",
    "offre": "Proposition reçue",
    "acceptee": "Proposition acceptée",
    "refusee": "Refus de l'entreprise",
    "sans_reponse": "Pas de réponse",
    "expiree": "Offre fermée avant candidature",
}

SITES_SCRAPING = ("linkedin", "indeed", "glassdoor")


# ---------------------------------------------------------------- utilitaires

def charger_prefs(strict: bool = True) -> dict:
    """Lit preferences.yml. Sans fichier : arrêt avec un message clair (strict) ou préférences d'exemple."""
    source = PREFS if PREFS.exists() else EXEMPLES / "preferences.exemple.yml"
    if not PREFS.exists() and strict:
        sys.exit("preferences.yml introuvable. Lance d'abord ./installer.sh, puis configure ton profil :\n"
                 "  - dans Claude Code : /configurer\n  - ou dans le navigateur : ./jobs serveur → « Mon profil »")
    with source.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def profil_configure(prefs: dict | None = None) -> bool:
    """Faux tant que le profil d'exemple n'a pas été rempli."""
    prefs = prefs if prefs is not None else charger_prefs(strict=False)
    nom = str((prefs.get("profil") or {}).get("nom") or "")
    return PREFS.exists() and bool(nom.strip()) and "Prénom" not in nom


def prenom(prefs: dict | None = None) -> str:
    nom = str(((prefs or charger_prefs(strict=False)).get("profil") or {}).get("nom") or "").split()
    return nom[0] if nom and "Prénom" not in nom[0] else "la personne"


def sans_accents(texte: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def contient_mot(texte: str, mot: str) -> bool:
    """Mot entier, insensible à la casse et aux accents."""
    t, m = sans_accents(texte), sans_accents(mot)
    return re.search(r"(?<![\w])" + re.escape(m) + r"(?![\w])", t) is not None


def nouvel_id(url: str, titre: str, entreprise: str) -> str:
    cle = url or f"{titre}|{entreprise}"
    return hashlib.sha1(cle.encode()).hexdigest()[:8]


def cle_doublon(titre: str, entreprise: str) -> str:
    return re.sub(r"\W+", " ", sans_accents(f"{entreprise} {titre}")).strip()


def aujourdhui() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------- suivi.csv

@contextmanager
def verrou():
    """Empêche deux commandes (ou deux agents) d'écrire suivi.csv en même temps."""
    chemin = DONNEES / "data" / ".verrou"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def lire_suivi() -> list[dict]:
    if not SUIVI.exists():
        return []
    with SUIVI.open(encoding="utf-8-sig", newline="") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    for l in lignes:
        for c in COLONNES:
            l.setdefault(c, "")
    return lignes


def ecrire_suivi(lignes: list[dict]) -> None:
    tmp = SUIVI.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(lignes)
    tmp.replace(SUIVI)


def trouver(lignes: list[dict], ident: str) -> dict:
    res = [l for l in lignes if l["id"].startswith(ident)]
    if len(res) != 1:
        sys.exit(f"Offre '{ident}' introuvable ou ambiguë ({len(res)} résultats).")
    return res[0]


def enregistrer_offres(offres: list[dict]) -> tuple[int, int]:
    """Ajoute les nouvelles offres au suivi sans toucher aux statuts existants."""
    with verrou():
        return _enregistrer_offres(offres)


def _enregistrer_offres(offres: list[dict]) -> tuple[int, int]:
    lignes = lire_suivi()
    ids = {l["id"] for l in lignes}
    cles = {cle_doublon(l["titre"], l["entreprise"]) for l in lignes}
    DOSSIER_OFFRES.mkdir(parents=True, exist_ok=True)
    ajoutees = doublons = 0
    for o in offres:
        cle = cle_doublon(o["titre"], o["entreprise"])
        if o["id"] in ids or cle in cles:
            doublons += 1
            continue
        description = o.pop("description", "") or ""
        (DOSSIER_OFFRES / f"{o['id']}.json").write_text(
            json.dumps({**o, "description": description}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        ligne = {c: "" for c in COLONNES}
        ligne.update({k: str(v) for k, v in o.items() if k in COLONNES and v is not None})
        ligne.update(date_ajout=aujourdhui(), date_maj=aujourdhui(), statut="nouvelle")
        lignes.append(ligne)
        ids.add(o["id"])
        cles.add(cle)
        ajoutees += 1
    ecrire_suivi(lignes)
    return ajoutees, doublons


# ---------------------------------------------------------------- filtres

def raison_rejet(titre: str, lieu: str, teletravail: bool, prefs: dict, entreprise: str = "") -> str | None:
    """Raison pour laquelle les filtres de preferences.yml écartent une offre, ou None. Une liste vide ne filtre rien."""
    mots = prefs.get("mots_cles_titre") or {}
    for e in prefs.get("entreprises_exclues") or []:
        if entreprise and contient_mot(entreprise, e):
            return f"entreprise exclue « {e} »"
    for m in mots.get("negatifs") or []:
        if contient_mot(titre, m):
            return f"mot exclu « {m} »"
    positifs = mots.get("positifs") or []
    if positifs and not any(contient_mot(titre, m) for m in positifs):
        return "titre hors cible"
    loc = prefs.get("localisation") or {}
    zones = loc.get("zones_acceptees") or []
    if lieu and zones:
        en_zone = any(contient_mot(lieu, z) for z in zones)
        en_france = contient_mot(lieu, loc.get("pays") or "France") or contient_mot(lieu, "FR")
        if not en_zone and not (teletravail and loc.get("teletravail_complet_france") and en_france):
            return f"lieu hors zone ({lieu})"
    return None


# ---------------------------------------------------------------- recherche

def lire_etat() -> dict:
    if ETAT.exists():
        return json.loads(ETAT.read_text(encoding="utf-8"))
    return {}


def ecrire_etat(etat: dict) -> None:
    ETAT.parent.mkdir(parents=True, exist_ok=True)
    ETAT.write_text(json.dumps(etat, indent=2), encoding="utf-8")


def valeur(x):
    """Convertit les valeurs pandas (NaN, NaT) en chaîne propre."""
    if x is None:
        return ""
    try:
        import pandas as pd
        if pd.isna(x):
            return ""
    except (TypeError, ValueError):
        pass
    return str(x).strip()


def cmd_chercher(args) -> None:
    try:
        from jobspy import scrape_jobs
    except ImportError:
        sys.exit("Module jobspy manquant : lance ./installer.sh")

    prefs = charger_prefs()
    lim = prefs.get("limites") or {}
    for cle, defaut in (("resultats_par_recherche", 15), ("recherches_max_par_session", 2), ("pause_secondes", [10, 25]),
                        ("delai_minimum_heures", 24), ("offres_publiees_depuis_jours", 7), ("descriptions_linkedin", True)):
        lim.setdefault(cle, defaut)
    sites = [s.strip() for s in args.sites.split(",") if s.strip()]
    inconnus = set(sites) - set(SITES_SCRAPING)
    if inconnus:
        sys.exit(f"Sites inconnus : {', '.join(inconnus)}. Choix : {', '.join(SITES_SCRAPING)}")

    etat = lire_etat()
    delai = timedelta(hours=lim["delai_minimum_heures"])
    autorises = []
    for s in sites:
        dernier = etat.get(s)
        if dernier and datetime.now() - datetime.fromisoformat(dernier) < delai:
            prochain = datetime.fromisoformat(dernier) + delai
            print(f"⏸  {s} : déjà interrogé récemment, prochain passage possible le {prochain:%d/%m à %Hh%M}.")
        else:
            autorises.append(s)
    if not autorises:
        print("Aucun site à interroger pour l'instant (garde-fou anti-blocage).")
        return

    toutes = prefs.get("recherches") or []
    if not toutes and not args.requete:
        sys.exit("Aucune requête dans preferences.yml (section « recherches »). Ajoute-en, ou utilise --requete \"...\".")
    n = lim["recherches_max_par_session"]
    if args.requete:
        requetes = [args.requete]
    else:  # rotation : chaque lancement prend les requêtes suivantes de la liste
        debut = etat.get("rotation", 0) % len(toutes)
        requetes = [toutes[(debut + k) % len(toutes)] for k in range(min(n, len(toutes)))]
        etat["rotation"] = (debut + n) % len(toutes)
    loc = prefs.get("localisation") or {}
    lieu = loc.get("ville_recherche") or prefs["profil"].get("ville") or "France"
    pays = loc.get("pays") or "France"
    pause_min, pause_max = lim["pause_secondes"]

    trouvees, rejets = [], {}
    premier = True
    for site in autorises:
        for q in requetes:
            if not premier:
                attente = random.uniform(pause_min, pause_max)
                print(f"   … pause {attente:.0f}s")
                time.sleep(attente)
            premier = False
            print(f"🔎 {site} : « {q} » à {lieu}")
            try:
                df = scrape_jobs(
                    site_name=[site],
                    search_term=q,
                    location=lieu,
                    results_wanted=lim["resultats_par_recherche"],
                    hours_old=lim["offres_publiees_depuis_jours"] * 24,
                    country_indeed=pays,
                    fetch_description=bool(lim.get("descriptions_linkedin")),
                    description_format="markdown",
                    verbose=0,
                )
            except Exception as e:  # le site a bloqué ou changé : on s'arrête là pour ce site
                print(f"   ⚠️  {site} a refusé ou échoué ({type(e).__name__}: {str(e)[:120]}). On passe.")
                break
            for _, r in df.iterrows():
                titre, entreprise = valeur(r.get("title")), valeur(r.get("company"))
                lieu_o = valeur(r.get("location"))
                remote = valeur(r.get("is_remote")).lower() == "true"
                rej = raison_rejet(titre, lieu_o, remote, prefs, entreprise)
                if not rej and valeur(r.get("job_type")).lower() == "internship":
                    rej = "contrat de stage"
                if rej:
                    rejets[rej] = rejets.get(rej, 0) + 1
                    continue
                url = valeur(r.get("job_url"))
                mini, maxi = valeur(r.get("min_amount")), valeur(r.get("max_amount"))
                salaire = f"{mini}-{maxi} {valeur(r.get('currency'))} / {valeur(r.get('interval'))}" if mini or maxi else ""
                trouvees.append({
                    "id": nouvel_id(url, titre, entreprise),
                    "source": site,
                    "titre": titre,
                    "entreprise": entreprise,
                    "lieu": lieu_o,
                    "contrat": valeur(r.get("job_type")),
                    "teletravail": "oui" if remote else "",
                    "salaire": salaire,
                    "url": url,
                    "url_directe": valeur(r.get("job_url_direct")),
                    "date_publication": valeur(r.get("date_posted")),
                    "description": valeur(r.get("description")),
                })
            print(f"   {len(df)} résultats reçus")
        etat[site] = datetime.now().isoformat(timespec="minutes")
    ecrire_etat(etat)

    ajoutees, doublons = enregistrer_offres(trouvees)
    print(f"\n✅ {ajoutees} nouvelle(s) offre(s) ajoutée(s) au suivi, {doublons} déjà connue(s).")
    if rejets:
        print("   Écartées par les filtres : " + ", ".join(f"{n}× {k}" for k, n in sorted(rejets.items(), key=lambda x: -x[1])[:6]))
    generer_tableau()
    if ajoutees:
        print("   Étape suivante : dans Claude Code, tape /analyser.")


def cmd_ajouter(args) -> None:
    prefs = charger_prefs()
    description = ""
    if args.description_fichier:
        description = Path(args.description_fichier).read_text(encoding="utf-8")
    source = args.source or ("welcometothejungle" if "welcometothejungle" in args.url else "manuel")
    o = {
        "id": nouvel_id(args.url, args.titre, args.entreprise),
        "source": source, "titre": args.titre, "entreprise": args.entreprise,
        "lieu": args.lieu or "", "contrat": args.contrat or "", "teletravail": args.teletravail or "",
        "salaire": args.salaire or "", "url": args.url, "description": description,
    }
    rej = raison_rejet(o["titre"], o["lieu"], False, prefs, o["entreprise"])
    if rej:
        print(f"ℹ️  Note : les filtres auraient écarté cette offre ({rej}). Ajoutée quand même.")
    ajoutees, _ = enregistrer_offres([o])
    print(f"✅ Offre ajoutée (id {o['id']})." if ajoutees else "Déjà dans le suivi.")
    generer_tableau()


def _texte_html(fragment: str) -> str:
    import html as html_mod
    t = re.sub(r"<(br|/p|/li|/h\d|/div)[^>]*>", "\n", fragment or "", flags=re.I)
    t = html_mod.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"[ \t\xa0]+", " ", re.sub(r"\n\s*\n+", "\n\n", t)).strip()


def lire_page_offre(url: str) -> dict:
    """Essaie de lire titre, entreprise, lieu, contrat et description sur la page publique d'une offre.
    Utilise les données structurées JobPosting (JSON-LD) quand elles existent, sinon le titre de la page.
    Ne lève jamais d'erreur : renvoie ce qu'il a pu trouver (souvent rien pour LinkedIn ou les pages en JavaScript)."""
    import html as html_mod
    info: dict = {}
    try:
        import requests  # certificats de certifi (le Python de macOS n'en a pas par défaut)
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0 (Macintosh) claude-jobs", "Accept-Language": "fr,en"})
        r.raise_for_status()
        page = r.text[:3_000_000]
    except Exception:
        return info

    def postes(x):
        if isinstance(x, list):
            for y in x:
                yield from postes(y)
        elif isinstance(x, dict):
            t = x.get("@type")
            if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                yield x
            for v in x.values():
                if isinstance(v, (dict, list)):
                    yield from postes(v)

    for bloc in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            jp = next(postes(json.loads(bloc.strip())), None)
        except (json.JSONDecodeError, ValueError):
            continue
        if not jp:
            continue
        org = jp.get("hiringOrganization")
        lieu = jp.get("jobLocation")
        lieu = lieu[0] if isinstance(lieu, list) and lieu else lieu
        adr = lieu.get("address", {}) if isinstance(lieu, dict) else {}
        adr = adr if isinstance(adr, dict) else {}
        contrat = jp.get("employmentType")
        info = {
            "titre": html_mod.unescape(str(jp.get("title") or "")).strip(),
            "entreprise": html_mod.unescape(str(org.get("name") if isinstance(org, dict) else org or "")).strip(),
            "lieu": ", ".join(str(v) for v in (adr.get("addressLocality"), adr.get("addressCountry")) if v and isinstance(v, str)),
            "contrat": ", ".join(contrat) if isinstance(contrat, list) else str(contrat or ""),
            "description": _texte_html(str(jp.get("description") or "")),
        }
        for cle, nom in (("datePosted", "Publiée le"), ("validThrough", "Date limite")):
            if jp.get(cle):
                info["description"] += f"\n\n{nom} : {str(jp[cle])[:10]}"
        break
    if not info.get("titre"):
        m = (re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', page, re.I)
             or re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I))
        if m:
            info["titre"] = html_mod.unescape(re.sub(r"\s+", " ", m.group(1))).strip()[:200]
    if not info.get("description"):
        m = re.search(r'<meta[^>]+(?:name|property)="(?:og:)?description"[^>]+content="([^"]+)"', page, re.I)
        if m:
            info["description"] = html_mod.unescape(m.group(1)).strip()
    return {k: v for k, v in info.items() if v}


def ajouter_depuis_page(d: dict) -> dict:
    """Ajout d'une offre depuis le tableau de bord (route /api/ajouter), sans passer par Claude.
    Les champs remplis à la main l'emportent sur ceux lus sur la page. Si l'offre est déjà suivie,
    seul son statut est mis à jour."""
    url = str(d.get("url") or "").strip()
    if not re.match(r"https?://\S+$", url):
        raise ValueError("Colle un lien complet (https://…).")
    statut = str(d.get("statut") or "postulee")
    if statut not in STATUTS:
        raise ValueError("Statut inconnu.")
    lu = lire_page_offre(url) if not (d.get("titre") and d.get("entreprise")) else {}
    champ = lambda k: str(d.get(k) or "").strip() or lu.get(k, "")
    titre, entreprise = champ("titre"), champ("entreprise")
    if not titre or not entreprise:
        manque = " et ".join(n for n, v in (("le titre", titre), ("l'entreprise", entreprise)) if not v)
        raise ValueError(f"Impossible de lire {manque} sur la page (site en JavaScript ou protégé) : remplis-les à la main.")
    o = {
        "id": nouvel_id(url, titre, entreprise), "source": "ajout manuel", "titre": titre, "entreprise": entreprise,
        "lieu": champ("lieu"), "contrat": champ("contrat"), "teletravail": "", "salaire": str(d.get("salaire") or "").strip(),
        "url": url, "description": str(d.get("description") or "").strip() or lu.get("description", ""),
    }
    ajoutees, _ = enregistrer_offres([dict(o)])
    if ajoutees:
        ident = o["id"]
    else:  # déjà suivie : retrouver la ligne (même lien, ou même entreprise + titre)
        cle = cle_doublon(titre, entreprise)
        ligne = next((l for l in lire_suivi() if l["url"] == url or l["id"] == o["id"]
                      or cle_doublon(l["titre"], l["entreprise"]) == cle), None)
        if not ligne:
            raise ValueError("Offre déjà présente mais introuvable.")
        ident = ligne["id"]
    note = str(d.get("note") or "").strip()
    note = ("Ajoutée à la main depuis le tableau de bord" if ajoutees else "Déjà suivie") + (f" — {note}" if note else "")
    offre = maj_statut(ident, statut, note, str(d.get("action") or "").strip() or None)
    return {"offre": offre, "nouvelle": bool(ajoutees), "lu_sur_la_page": sorted(lu)}


def cmd_noter(args) -> None:
    with verrou():
        _cmd_noter(args)


def _cmd_noter(args) -> None:
    lignes = lire_suivi()
    l = trouver(lignes, args.id)
    if not 0 <= args.score <= 100:
        sys.exit("Le score doit être entre 0 et 100.")
    l["score"] = str(args.score)
    l["resume"] = args.resume or l["resume"]
    if args.ecarter:
        l["statut"] = "ecartee"
    elif l["statut"] == "nouvelle":
        l["statut"] = "a_etudier"
    l["date_maj"] = aujourdhui()
    ecrire_suivi(lignes)
    generer_tableau()
    print(f"✅ {l['titre']} — {l['entreprise']} : {args.score}/100 ({l['statut']})")


def maj_statut(ident: str, statut: str, note: str | None = None, action: str | None = None) -> dict:
    """Change le statut d'une offre (utilisé par la ligne de commande et par le tableau de bord)."""
    if statut not in STATUTS:
        raise ValueError("Statut inconnu. Choix : " + ", ".join(STATUTS))
    with verrou():
        lignes = lire_suivi()
        res = [l for l in lignes if l["id"].startswith(ident)]
        if len(res) != 1:
            raise ValueError(f"Offre '{ident}' introuvable ou ambiguë ({len(res)} résultats).")
        l = res[0]
        l["statut"] = statut
        l["date_maj"] = aujourdhui()
        premiere_candidature = statut == "postulee" and not l["date_candidature"]
        if premiere_candidature:
            l["date_candidature"] = aujourdhui()
        if action:
            l["prochaine_action"] = action
        elif premiere_candidature:
            l["prochaine_action"] = f"Relancer le {(date.today() + timedelta(days=7)).isoformat()}"
        elif action is not None:  # champ vidé volontairement
            l["prochaine_action"] = ""
        if note:
            l["notes"] = (l["notes"] + " | " if l["notes"] else "") + f"{aujourdhui()} : {note}"
        ecrire_suivi(lignes)
    generer_tableau()
    return l


def maj_lien(ident: str, lien: str | None, canal: str | None) -> dict:
    """Enregistre le lien direct pour postuler (« - » pour l'effacer) et/ou la façon de postuler."""
    with verrou():
        lignes = lire_suivi()
        l = trouver(lignes, ident)
        if lien is not None:
            l["lien_postuler"] = "" if lien == "-" else lien
        if canal is not None:
            l["canal"] = canal
        l["date_maj"] = aujourdhui()
        ecrire_suivi(lignes)
    generer_tableau()
    return l


def cmd_lien(args) -> None:
    l = maj_lien(args.id, args.url, args.canal)
    print(f"✅ {l['titre']} — {l['entreprise']} : postuler → {l['lien_postuler'] or '(pas de lien direct)'}"
          + (f" · {l['canal']}" if l["canal"] else ""))


def cmd_statut(args) -> None:
    try:
        l = maj_statut(args.id, args.statut, args.note, args.action)
    except ValueError as e:
        sys.exit(str(e))
    print(f"✅ {l['titre']} — {l['entreprise']} → {args.statut}")


def cmd_liste(args) -> None:
    lignes = lire_suivi()
    if args.statut:
        lignes = [l for l in lignes if l["statut"] == args.statut]
    lignes.sort(key=lambda l: -int(l["score"] or -1))
    if not lignes:
        print("Aucune offre.")
        return
    for l in lignes:
        score = f"{l['score']:>3}" if l["score"] else "  -"
        print(f"{l['id']}  {score}  {l['statut']:<13} {l['titre'][:45]:<45}  {l['entreprise'][:25]:<25}  {l['source']}")


# ---------------------------------------------------------------- tableau HTML

RE_LIMITE = re.compile(
    r"(?:date limite|limite|jusqu['’]au|deadline|avant le|cl[ôo]ture)[^\d\n]{0,40}?(\d{1,2})/(\d{1,2})/(\d{4})", re.I)
RE_RELANCE = re.compile(r"Relancer le (\d{4}-\d{2}-\d{2})")
RE_CASE = re.compile(r"^(\s*[-*] \[)([ xX])(\].*)$")


def date_limite(description: str) -> str:
    """Première date limite de candidature trouvée dans la description (format ISO), sinon ''."""
    for m in RE_LIMITE.finditer(description or ""):
        j, mo, a = (int(x) for x in m.groups())
        try:
            return date(a, mo, j).isoformat()
        except ValueError:
            continue
    return ""


def avancement_checklist(texte: str) -> list[int] | None:
    cases = [RE_CASE.match(l) for l in texte.splitlines()]
    cases = [c for c in cases if c]
    if not cases:
        return None
    return [sum(c.group(2) in "xX" for c in cases), len(cases)]


def lire_description(ident: str) -> str:
    f = DOSSIER_OFFRES / f"{ident}.json"
    if not f.exists():
        return ""
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("description", "") or ""
    except json.JSONDecodeError:
        return ""


def _json_html(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False).replace("</", "<\\/")


RE_CDD = re.compile(r"\bCDD\b|contractuel|dur[ée]e d[ée]termin[ée]e|fixed[- ]term|temporary|\bcontract\b|contrat de projet|int[ée]rim", re.I)


def est_cdd(l: dict, description: str = "") -> bool:
    """CDD si le contrat le dit ; si le contrat est vague (« fulltime », « Temps plein », vide) et ne dit pas CDI,
    on regarde la description."""
    contrat = l.get("contrat", "")
    if RE_CDD.search(contrat):
        return True
    if re.search(r"\bCDI\b|permanent", contrat, re.I):
        return False
    return bool(re.search(r"\bCDD\b|contrat à durée déterminée|fixed[- ]term contract"
                          r"|\b(?:pour|durée\s*:?|d'une durée de)\s*\d+\s*mois", description, re.I))


def generer_tableau() -> None:
    """Régénère tableau_de_bord.html et une page par offre (pages/<id>.html)."""
    lignes = lire_suivi()
    prefs = charger_prefs(strict=False)
    config = {"nom": str((prefs.get("profil") or {}).get("nom") or ""), "configure": profil_configure(prefs), "port": PORT}
    details = {}
    for l in lignes:
        dossier = CANDIDATURES / l["id"]
        l["dossier"] = f"candidatures/{l['id']}/" if dossier.exists() else ""
        l["fichiers"] = (sorted(p.name for p in dossier.iterdir() if p.is_file() and not p.name.startswith("."))
                         if dossier.exists() else [])
        textes = {f: (dossier / f).read_text(encoding="utf-8") for f in l["fichiers"] if f.endswith(".md")}
        description = lire_description(l["id"])
        l["checklist"] = avancement_checklist(textes.get("checklist.md", ""))
        l["date_limite"] = date_limite(description)
        m = RE_RELANCE.search(l["prochaine_action"])
        l["relance"] = m.group(1) if m else ""
        l["a_completer"] = sum(t.count("[À COMPLÉTER") for t in textes.values())
        l["page"] = f"pages/{l['id']}.html"
        l["type"] = "cdd" if est_cdd(l, description) else "cdi"
        details[l["id"]] = (description, textes)
    maj = datetime.now().strftime("%d/%m/%Y %H:%M")
    modele = (RACINE / "modele_tableau.html").read_text(encoding="utf-8")
    DONNEES.mkdir(parents=True, exist_ok=True)
    TABLEAU.write_text(modele.replace("/*__DONNEES__*/null", _json_html(
        {"offres": lignes, "statuts": STATUTS, "maj": maj, "config": config})), encoding="utf-8")

    # pages dédiées : ordre de navigation = score décroissant, offres écartées à la fin
    fermees = ("ecartee", "expiree")
    ordre = sorted(lignes, key=lambda l: (l["statut"] in fermees, -(int(l["score"]) if l["score"].isdigit() else -1)))
    ordre = [{"id": l["id"], "titre": l["titre"], "entreprise": l["entreprise"]} for l in ordre]
    modele_offre = (RACINE / "modele_offre.html").read_text(encoding="utf-8")
    PAGES.mkdir(exist_ok=True)
    for l in lignes:
        description, textes = details[l["id"]]
        donnees = {"offre": l, "description": description, "textes": textes, "statuts": STATUTS,
                   "ordre": ordre, "maj": maj, "retour": "../tableau_de_bord.html", "config": config}
        (PAGES / f"{l['id']}.html").write_text(
            modele_offre.replace("/*__DONNEES__*/null", _json_html(donnees)), encoding="utf-8")
    ids = {l["id"] for l in lignes}
    for p in PAGES.glob("*.html"):  # pages d'offres supprimées du suivi
        if p.stem not in ids:
            p.unlink()


# ---------------------------------------------------------------- Claude Code depuis la page d'une offre

CLAUDE_OUTILS = ["Read", "Edit", "Write", "Glob", "Grep", "WebSearch", "WebFetch",
                 "Bash(./jobs:*)", "Bash(curl:*)", "Bash(mkdir:*)", "Bash(ls:*)"]
CLAUDE_DUREE_MAX = 25 * 60  # secondes


def _claude_bin() -> str:
    import shutil
    for c in (shutil.which("claude"), str(Path.home() / ".local/bin/claude"), "/opt/homebrew/bin/claude", "/usr/local/bin/claude"):
        if c and Path(c).exists():
            return c
    raise ValueError("Commande « claude » introuvable : installe Claude Code (https://claude.com/claude-code), "
                     "ou prépare le dossier depuis Claude Code avec /dossier <id>.")


def _pid_vivant(pid: int) -> bool:
    import os
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def etat_tache(ident: str) -> dict:
    """État de la dernière tâche Claude pour cette offre (en_cours, termine, erreur), avec la fin du journal."""
    f = TACHES / f"{ident}.json"
    if not f.exists():
        return {"etat": "aucune"}
    e = json.loads(f.read_text(encoding="utf-8"))
    if e.get("etat") == "en_cours" and not _pid_vivant(e.get("pid")):  # serveur redémarré pendant la tâche
        e.update(etat="termine", fin=datetime.now().strftime("%Y-%m-%d %H:%M"), remarque="fin détectée après coup")
        f.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    journal = TACHES / f"{ident}.log"
    e["journal"] = journal.read_text(encoding="utf-8", errors="replace")[-4000:] if journal.exists() else ""
    return e


def _consigne_claude(l: dict, reponses: list[dict], consignes: str) -> tuple[str, str]:
    ident, dossier = l["id"], CANDIDATURES / l["id"]
    qui = prenom()
    entete = (f"Tu es lancé en arrière-plan par le bouton de la page de l'offre {ident} (« {l['titre']} », {l['entreprise']}). "
              f"{qui} n'est pas là pour répondre : ne pose aucune question, décide seul en respectant CLAUDE.md, et écris "
              "`[À COMPLÉTER : …]` pour toute information qui manque. Ne soumets jamais de candidature, ne te connecte à aucun compte. "
              f"Commence par lire CLAUDE.md, PIPELINE.md, journal.md (s'il existe), cv.md, preferences.yml et data/offres/{ident}.json.\n\n")
    if not dossier.exists() or not any(dossier.glob("*.md")):
        mode = "preparer"
        corps = (f"Prépare le dossier {ident}, exactement comme décrit dans la section « Prépare le dossier » de CLAUDE.md. "
                 f"Relis la page de l'offre si la description est résumée. Lance `./jobs cv {ident}` (cv.pdf) et `./jobs lettre {ident}` s'il y a une `lettre.md`, "
                 f"`./jobs lien {ident} …` si le lien pour postuler n'est pas celui de l'offre, puis "
                 f"`./jobs statut {ident} dossier_pret --action \"Relire le dossier puis postuler\"`.")
    else:
        mode = "completer"
        lignes = [f"- {r['question'].strip()}\n  → Réponse : {r['reponse'].strip()}" for r in reponses if r.get("reponse", "").strip()]
        corps = (f"Complète le dossier existant candidatures/{ident}/.\n\n"
                 + (f"Réponses de {qui} aux `[À COMPLÉTER]` :\n" + "\n".join(lignes) + "\n\n" if lignes else "")
                 + (f"Autres consignes de {qui} : {consignes.strip()}\n\n" if consignes.strip() else "")
                 + "À faire :\n"
                 "1. Intègre ces réponses dans tous les fichiers du dossier concernés (lettre, CV, réponses, fiche, checklist) et retire "
                 "les `[À COMPLÉTER]` résolus. Laisse ceux qui n'ont pas de réponse. Une réponse comme « non » ou « rien » veut dire : "
                 "retirer la mention ou la phrase concernée.\n"
                 "2. Si une réponse apporte un fait nouveau sur le parcours, ajoute-le aussi à cv.md, section "
                 "« Précisions », avec la date du jour.\n"
                 f"3. Si lettre.md a changé : `./jobs lettre {ident}` ; si cv.md a changé : `./jobs cv {ident}`.\n"
                 f"4. Ne change pas le statut. Ajoute une note : `./jobs statut {ident} {l['statut']} --note \"Dossier complété par Claude (bouton) : <ce qui a changé>\"`.")
    fin = ("\n\nTermine par un compte rendu en français de 3 à 6 lignes, sans Markdown lourd : ce que tu as fait, les fichiers modifiés, "
           "et ce qui reste à compléter ou à vérifier avant l'envoi.")
    return mode, entete + corps + fin


def lancer_claude(ident: str, reponses: list[dict] | None = None, consignes: str = "") -> dict:
    """Lance Claude Code (claude -p) en arrière-plan pour préparer ou compléter le dossier d'une offre."""
    import subprocess
    import threading
    if not re.fullmatch(r"[0-9a-f]{8}", ident):
        raise ValueError("Identifiant invalide.")
    if DONNEES != RACINE:
        raise ValueError("Pas disponible dans la démo : configure ton propre profil pour utiliser ce bouton.")
    l = next((x for x in lire_suivi() if x["id"] == ident), None)
    if l is None:
        raise ValueError("Offre introuvable dans suivi.csv.")
    if etat_tache(ident).get("etat") == "en_cours":
        raise ValueError("Claude travaille déjà sur ce dossier.")
    mode, consigne = _consigne_claude(l, reponses or [], consignes or "")
    TACHES.mkdir(parents=True, exist_ok=True)
    journal = TACHES / f"{ident}.log"
    etat_f = TACHES / f"{ident}.json"
    sortie = open(journal, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [_claude_bin(), "-p", consigne, "--output-format", "text", "--permission-mode", "acceptEdits",
         "--allowedTools", *CLAUDE_OUTILS],
        cwd=RACINE, stdout=sortie, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    etat = {"etat": "en_cours", "mode": mode, "pid": proc.pid, "debut": datetime.now().strftime("%Y-%m-%d %H:%M"), "fin": ""}
    etat_f.write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")

    def attendre() -> None:
        try:
            code = proc.wait(timeout=CLAUDE_DUREE_MAX)
        except subprocess.TimeoutExpired:
            proc.kill(); code = "délai dépassé"
        sortie.close()
        etat.update(etat="termine" if code == 0 else "erreur", fin=datetime.now().strftime("%Y-%m-%d %H:%M"), code=code)
        etat_f.write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")

    threading.Thread(target=attendre, daemon=True).start()
    return etat


def cocher_checklist(ident: str, ligne: int, coche: bool) -> str:
    """Coche ou décoche la case de la ligne `ligne` (0 = première) de candidatures/<id>/checklist.md."""
    if not re.fullmatch(r"[0-9a-f]{8}", ident):
        raise ValueError("Identifiant invalide.")
    f = CANDIDATURES / ident / "checklist.md"
    if not f.exists():
        raise ValueError("Pas de checklist pour cette offre.")
    lignes = f.read_text(encoding="utf-8").split("\n")
    if not 0 <= ligne < len(lignes) or not (m := RE_CASE.match(lignes[ligne])):
        raise ValueError("Cette ligne n'est pas une case à cocher (le fichier a peut-être changé : recharge la page).")
    lignes[ligne] = m.group(1) + ("x" if coche else " ") + m.group(3)
    f.write_text("\n".join(lignes), encoding="utf-8")
    generer_tableau()
    return "\n".join(lignes)


def cmd_tableau(args) -> None:
    generer_tableau()
    print(f"✅ {TABLEAU}")


# ---------------------------------------------------------------- lettres PDF

def ville_lettre() -> str:
    """Ville écrite avant la date de la lettre : « Lyon » pour « Lyon, France »."""
    return str(charger_prefs(strict=False).get("profil", {}).get("ville") or "").split(",")[0].strip() or "Paris"


def enregistrer_lettre(ident: str, texte: str) -> str:
    """Page de l'offre : enregistre le texte modifié dans lettre.md et régénère lettre.pdf (mise en page du modèle).
    En cas d'erreur de mise en page, lettre.md n'est pas modifié."""
    from lettre_pdf import generer
    dossier = CANDIDATURES / ident
    if not re.fullmatch(r"[0-9a-f]{8}", ident) or not dossier.is_dir():
        raise ValueError("Pas de dossier pour cette offre.")
    texte = texte.replace("\r\n", "\n").strip() + "\n"
    if len(texte) < 50:
        raise ValueError("Lettre vide ou trop courte.")
    source = dossier / "lettre.md"
    essai = dossier / ".lettre_essai.md"
    essai.write_text(texte, encoding="utf-8")
    try:
        generer(essai, dossier / "lettre.pdf", charger_prefs()["profil"], ville=ville_lettre())
    finally:
        essai.unlink(missing_ok=True)
    source.write_text(texte, encoding="utf-8")
    generer_tableau()
    return texte


def cmd_lettre(args) -> None:
    from lettre_pdf import generer
    profil = charger_prefs()["profil"]
    CANDIDATURES.mkdir(parents=True, exist_ok=True)
    ids = [d.name for d in sorted(CANDIDATURES.iterdir()) if (d / "lettre.md").exists()] if args.toutes else [args.id]
    if not ids or ids == [None]:
        sys.exit("Donne un id, ou --toutes.")
    for ident in ids:
        dossiers = [d for d in CANDIDATURES.iterdir() if d.name.startswith(ident)]
        if len(dossiers) != 1 or not (dossiers[0] / "lettre.md").exists():
            print(f"⚠️  Pas de lettre.md pour '{ident}'.")
            continue
        sortie = generer(dossiers[0] / "lettre.md", dossiers[0] / "lettre.pdf", profil, ville=ville_lettre())
        print(f"✅ {sortie.relative_to(DONNEES)}")
    generer_tableau()


def pdflatex_disponible() -> str:
    import shutil
    return shutil.which("pdflatex") or next((c for c in ("/Library/TeX/texbin/pdflatex", "/usr/bin/pdflatex") if Path(c).exists()), "")


def generer_cv(source: Path, sortie: Path) -> tuple[Path, int, str]:
    """cv.md → cv.pdf. Moteur (preferences.yml → cv.moteur) : « simple » (reportlab, rien à installer),
    « latex » (pdflatex, plus joli) ou « auto » (LaTeX s'il est installé). Renvoie (chemin, pages, moteur)."""
    reglages = charger_prefs(strict=False).get("cv") or {}
    moteur = str(reglages.get("moteur") or "auto").lower()
    couleur = str(reglages.get("couleur") or "1F3A5F").lstrip("#")
    if moteur == "latex" or (moteur == "auto" and pdflatex_disponible()):
        if not pdflatex_disponible():
            raise RuntimeError("pdflatex introuvable : installe MacTeX/BasicTeX (macOS) ou texlive (Linux), "
                               "ou mets « moteur: simple » dans la section cv de preferences.yml.")
        from cv_pdf import generer
        chemin, pages = generer(source, sortie, couleur=couleur)
        return chemin, pages, "latex"
    from cv_pdf_simple import generer
    chemin, pages = generer(source, sortie, couleur=couleur)
    return chemin, pages, "simple"


def cmd_cv(args) -> None:
    CANDIDATURES.mkdir(parents=True, exist_ok=True)
    ids = [d.name for d in sorted(CANDIDATURES.iterdir()) if (d / "cv.md").exists()] if args.toutes else [args.id]
    if not ids or ids == [None]:
        sys.exit("Donne un id, ou --toutes.")
    for ident in ids:
        dossiers = [d for d in CANDIDATURES.iterdir() if d.name.startswith(ident)]
        if len(dossiers) != 1 or not (dossiers[0] / "cv.md").exists():
            print(f"⚠️  Pas de cv.md pour '{ident}'.")
            continue
        try:
            sortie, pages, moteur = generer_cv(dossiers[0] / "cv.md", dossiers[0] / "cv.pdf")
        except RuntimeError as e:
            print(f"❌ {e}")
            continue
        alerte = f"  ⚠️ {pages} pages : raccourcir cv.md" if pages > 1 else ""
        print(f"✅ {sortie.relative_to(DONNEES)} (mise en page {moteur}){alerte}")
    generer_tableau()


# ---------------------------------------------------------------- serveur local (tableau de bord modifiable)

def cmd_serveur(args) -> None:
    import mimetypes
    import webbrowser
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import unquote, urlparse

    class Gestion(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silencieux
            pass

        def _repondre(self, code: int, corps: bytes, type_: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", type_)
            self.send_header("Content-Length", str(len(corps)))
            self.send_header("Cache-Control", "no-store")  # lettre.pdf / cv.pdf régénérés depuis la page
            self.end_headers()
            self.wfile.write(corps)

        def do_GET(self):
            chemin = unquote(urlparse(self.path).path)
            if chemin in ("/", "/tableau_de_bord.html"):
                generer_tableau()
                return self._repondre(200, TABLEAU.read_bytes(), "text/html; charset=utf-8")
            if chemin == "/profil":
                return self._repondre(200, page_profil().encode(), "text/html; charset=utf-8")
            if chemin == "/api/tache":
                from urllib.parse import parse_qs
                ident = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
                corps = {"ok": True, **etat_tache(ident)} if re.fullmatch(r"[0-9a-f]{8}", ident) else {"ok": False, "erreur": "id invalide"}
                return self._repondre(200, json.dumps(corps, ensure_ascii=False).encode(), "application/json")
            if m := re.fullmatch(r"/pages/([0-9a-f]{8})\.html", chemin):
                generer_tableau()  # toujours à jour (fichiers du dossier modifiés entre-temps)
                page = PAGES / f"{m.group(1)}.html"
                if page.exists():
                    return self._repondre(200, page.read_bytes(), "text/html; charset=utf-8")
            fichier = (DONNEES / chemin.lstrip("/")).resolve()
            # seuls les dossiers de candidature sont servis
            if CANDIDATURES.resolve() in fichier.parents and fichier.is_file():
                type_ = mimetypes.guess_type(fichier.name)[0] or "text/plain"
                if type_.startswith("text/") or fichier.suffix == ".md":
                    type_ = "text/plain; charset=utf-8"
                return self._repondre(200, fichier.read_bytes(), type_)
            self._repondre(404, b"Introuvable", "text/plain")

        def do_POST(self):
            route = urlparse(self.path).path
            if route not in ("/api/statut", "/api/checklist", "/api/ouvrir", "/api/completer", "/api/lettre", "/api/ajouter",
                             "/api/profil"):
                return self._repondre(404, b"{}", "application/json")
            try:
                n = int(self.headers.get("Content-Length", 0))
                d = json.loads(self.rfile.read(n) or b"{}")
                ident = str(d.get("id", ""))
                if route == "/api/statut":
                    res = {"offre": maj_statut(ident, str(d.get("statut", "")), d.get("note") or None, d.get("action"))}
                elif route == "/api/completer":
                    reps = [r for r in d.get("reponses") or [] if isinstance(r, dict)]
                    res = {"tache": lancer_claude(ident, reps, str(d.get("consignes") or ""))}
                elif route == "/api/checklist":
                    res = {"texte": cocher_checklist(ident, int(d.get("ligne", -1)), bool(d.get("coche")))}
                elif route == "/api/lettre":
                    res = {"texte": enregistrer_lettre(ident, str(d.get("texte") or ""))}
                elif route == "/api/ajouter":
                    res = ajouter_depuis_page(d)
                elif route == "/api/profil":
                    res = enregistrer_profil(d)
                else:  # ouvrir le dossier de candidature (Finder, explorateur de fichiers)
                    dossier = CANDIDATURES / ident
                    if not re.fullmatch(r"[0-9a-f]{8}", ident) or not dossier.is_dir():
                        raise ValueError("Pas de dossier pour cette offre.")
                    import subprocess
                    subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(dossier)], check=False)
                    res = {}
                self._repondre(200, json.dumps({"ok": True, **res}, ensure_ascii=False).encode(), "application/json")
            except (ValueError, TypeError, json.JSONDecodeError) as e:
                self._repondre(400, json.dumps({"ok": False, "erreur": str(e)}, ensure_ascii=False).encode(), "application/json")

    import os
    import threading

    url = f"http://127.0.0.1:{args.port}/" + ("" if profil_configure() or DONNEES != RACINE else "profil")
    try:
        serveur = ThreadingHTTPServer(("127.0.0.1", args.port), Gestion)
    except OSError:
        sys.exit(f"Le port {args.port} est déjà pris : le tableau de bord tourne sans doute déjà ({url}). "
                 f"Sinon : ./jobs serveur --port 8770")
    print(f"Tableau de bord : {url}  (Ctrl+C pour arrêter)")
    if not profil_configure() and DONNEES == RACINE:
        print("Premier lancement : remplis la page « Mon profil » qui vient de s'ouvrir (ou tape /configurer dans Claude Code).")
    if not args.sans_navigateur:
        webbrowser.open(url)

    # Si jobs.py est modifié (par Claude), le serveur se relance tout seul avec le nouveau code.
    code = Path(__file__).resolve()
    depart = code.stat().st_mtime
    relancer = threading.Event()

    def surveiller() -> None:
        while not relancer.is_set():
            time.sleep(2)
            try:
                if code.stat().st_mtime != depart:
                    relancer.set()
                    serveur.shutdown()
            except OSError:
                pass

    threading.Thread(target=surveiller, daemon=True).start()
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêté.")
        return
    finally:
        serveur.server_close()
    if relancer.is_set():
        print("jobs.py a changé : redémarrage du serveur…", flush=True)
        time.sleep(0.5)  # laisse finir l'écriture du fichier
        os.execv(sys.executable, [sys.executable, str(code), "serveur", "--sans-navigateur", "--port", str(args.port)])


# ---------------------------------------------------------------- profil (page « Mon profil » du tableau de bord)

def page_profil() -> str:
    prefs = charger_prefs(strict=False)
    cv = CV_REFERENCE.read_text(encoding="utf-8") if CV_REFERENCE.exists() else ""
    donnees = {"prefs": prefs, "cv": cv, "diagnostic": diagnostic(), "configure": profil_configure(prefs),
               "demo": DONNEES != RACINE}
    modele = (RACINE / "modele_profil.html").read_text(encoding="utf-8")
    return modele.replace("/*__DONNEES__*/null", _json_html(donnees))


ENTETE_PREFS = """# Tes préférences de recherche. Ce fichier est lu par ./jobs et par Claude.
# Modifiable à la main, depuis le tableau de bord (./jobs serveur → « Mon profil ») ou avec /configurer dans Claude Code.
# Exemple commenté : exemples/preferences.exemple.yml

"""


def ecrire_prefs(prefs: dict) -> None:
    PREFS.write_text(ENTETE_PREFS + yaml.safe_dump(prefs, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")


def enregistrer_profil(d: dict) -> dict:
    """Route /api/profil : fusionne les champs du formulaire dans preferences.yml et réécrit cv.md s'il est fourni."""
    if DONNEES != RACINE:
        raise ValueError("La démo ne s'enregistre pas : lance ./jobs serveur pour ton propre profil.")
    nouvelles = d.get("prefs")
    if not isinstance(nouvelles, dict):
        raise ValueError("Formulaire illisible.")
    prefs = charger_prefs(strict=False)

    def fusion(cible: dict, source: dict) -> None:
        for k, v in source.items():
            if isinstance(v, dict) and isinstance(cible.get(k), dict):
                fusion(cible[k], v)
            else:
                cible[k] = v

    fusion(prefs, nouvelles)
    if not str(prefs.get("profil", {}).get("nom") or "").strip():
        raise ValueError("Indique au moins ton nom.")
    ecrire_prefs(prefs)
    cv = d.get("cv")
    if isinstance(cv, str) and cv.strip():
        CV_REFERENCE.write_text(cv.replace("\r\n", "\n").strip() + "\n", encoding="utf-8")
    generer_tableau()
    return {"diagnostic": diagnostic(), "configure": profil_configure(prefs)}


# ---------------------------------------------------------------- vérification de l'installation

def diagnostic() -> list[dict]:
    """Liste de points vérifiés : {ok, obligatoire, titre, conseil}."""
    import importlib.util
    import shutil
    points = []

    def point(ok: bool, titre: str, conseil: str = "", obligatoire: bool = True) -> None:
        points.append({"ok": bool(ok), "titre": titre, "conseil": "" if ok else conseil, "obligatoire": obligatoire})

    manquants = [m for m in ("yaml", "reportlab", "requests") if importlib.util.find_spec(m) is None]
    point(not manquants, "Dépendances Python installées", "Lance ./installer.sh" + (f" (manque : {', '.join(manquants)})" if manquants else ""))
    point(importlib.util.find_spec("jobspy") is not None, "Recherche automatique LinkedIn / Indeed (python-jobspy)",
          "Facultatif : ./installer.sh l'installe ; sans lui, ./jobs chercher ne marche pas mais les agents de Claude, oui.", False)
    prefs = charger_prefs(strict=False)
    point(PREFS.exists(), "Fichier preferences.yml", "Lance ./installer.sh, puis /configurer dans Claude Code ou la page « Mon profil ».")
    point(profil_configure(prefs), "Profil rempli (nom, coordonnées)", "Remplis la page « Mon profil » ou tape /configurer dans Claude Code.")
    point(bool(prefs.get("postes_vises")) and bool(prefs.get("recherches")), "Postes visés et requêtes de recherche",
          "Indique au moins un poste visé et une requête de recherche.")
    cv = CV_REFERENCE.read_text(encoding="utf-8") if CV_REFERENCE.exists() else ""
    point(len(cv) > 300 and "[À REMPLIR" not in cv, "CV de référence (cv.md)",
          "Colle ton CV dans « Mon profil », ou donne ton CV (PDF) à Claude avec /configurer.")
    claude = shutil.which("claude") or next((c for c in (str(Path.home() / ".local/bin/claude"), "/opt/homebrew/bin/claude",
                                                          "/usr/local/bin/claude") if Path(c).exists()), "")
    point(bool(claude), "Claude Code installé (analyse des offres, dossiers)",
          "Installe Claude Code : https://claude.com/claude-code (abonnement Claude Pro ou Max, ou clé d'API).")
    point(bool(pdflatex_disponible()), "LaTeX (CV plus élégant)",
          "Facultatif : sans LaTeX, le CV PDF est fait avec une mise en page simple. macOS : brew install --cask basictex.", False)
    return points


def cmd_verifier(args) -> None:
    pts = diagnostic()
    for p in pts:
        signe = "✅" if p["ok"] else ("❌" if p["obligatoire"] else "➖")
        print(f"{signe} {p['titre']}" + (f"\n   → {p['conseil']}" if p["conseil"] else ""))
    manque = [p for p in pts if p["obligatoire"] and not p["ok"]]
    print("\nTout est prêt. Lance ./jobs serveur, puis /chercher dans Claude Code." if not manque
          else f"\n{len(manque)} point(s) à régler avant de commencer.")


# ---------------------------------------------------------------- démo (profil fictif)

def cmd_demo(args) -> None:
    """Copie demo/ dans .demo/ (à chaque fois, pour repartir de zéro), génère les PDF et ouvre le tableau de bord."""
    import shutil
    import subprocess
    cible = RACINE / ".demo"
    shutil.rmtree(cible, ignore_errors=True)
    shutil.copytree(RACINE / "demo", cible)
    # dates relatives : {{J-10}} → date ISO d'il y a 10 jours, {{J+5|fr}} → jj/mm/aaaa dans 5 jours
    def dater(m: re.Match) -> str:
        d = date.today() + timedelta(days=int(m.group(1)))
        return d.strftime("%d/%m/%Y") if m.group(2) else d.isoformat()
    for f in cible.rglob("*"):
        if f.is_file() and f.suffix in (".csv", ".json", ".md", ".yml"):
            f.write_text(re.sub(r"\{\{J([+-]?\d+)(\|fr)?\}\}", dater, f.read_text(encoding="utf-8")), encoding="utf-8")
    env = {**os.environ, "JOBS_DONNEES": str(cible)}
    for cmd in (["cv", "--toutes"], ["lettre", "--toutes"]):
        subprocess.run([sys.executable, str(Path(__file__).resolve()), *cmd], env=env, check=False,
                       stdout=subprocess.DEVNULL)
    print("Démo : profil fictif de Camille Martin. Rien de ce que tu fais ici n'est enregistré dans ton propre suivi.")
    if args.sans_serveur:
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "tableau"], env=env, check=False)
        print(f"Pages générées dans {cible}")
        return
    os.execve(sys.executable, [sys.executable, str(Path(__file__).resolve()), "serveur", "--port", str(args.port)]
              + (["--sans-navigateur"] if args.sans_navigateur else []), env)


# ---------------------------------------------------------------- CLI

def main() -> None:
    p = argparse.ArgumentParser(description="Recherche d'emploi et suivi des candidatures. Pour commencer : ./jobs verifier")
    sp = p.add_subparsers(dest="cmd", required=True)

    c = sp.add_parser("chercher", help="Recherche LinkedIn / Indeed / Glassdoor (avec garde-fous)")
    c.add_argument("--sites", default="linkedin,indeed", help="ex : linkedin,indeed (défaut). Glassdoor bloque presque toujours.")
    c.add_argument("--requete", help="une requête précise au lieu de celles de preferences.yml")
    c.set_defaults(f=cmd_chercher)

    a = sp.add_parser("ajouter", help="Ajouter une offre à la main")
    a.add_argument("url")
    a.add_argument("--titre", required=True)
    a.add_argument("--entreprise", required=True)
    a.add_argument("--lieu")
    a.add_argument("--contrat")
    a.add_argument("--salaire")
    a.add_argument("--teletravail", help="ex : fréquent, occasionnel, total")
    a.add_argument("--source")
    a.add_argument("--description-fichier", help="fichier texte contenant la description de l'offre")
    a.set_defaults(f=cmd_ajouter)

    n = sp.add_parser("noter", help="Enregistrer le score d'une offre")
    n.add_argument("id")
    n.add_argument("score", type=int)
    n.add_argument("--resume", help="résumé en une ligne de l'analyse")
    n.add_argument("--ecarter", action="store_true", help="marquer l'offre comme écartée")
    n.set_defaults(f=cmd_noter)

    s = sp.add_parser("statut", help="Changer le statut d'une offre")
    s.add_argument("id")
    s.add_argument("statut", help=" | ".join(STATUTS))
    s.add_argument("--note")
    s.add_argument("--action", help="prochaine action (ex : 'Entretien RH le 12/11')")
    s.set_defaults(f=cmd_statut)

    li = sp.add_parser("lien", help="Lien direct pour postuler et façon de postuler (affichés sur la page de l'offre)")
    li.add_argument("id")
    li.add_argument("url", nargs="?", help="lien du formulaire de candidature (« - » pour effacer)")
    li.add_argument("--canal", help="ex : 'Formulaire Welcome Kit (bouton APPLY NOW)' ou 'Pas de formulaire : LinkedIn'")
    li.set_defaults(f=cmd_lien)

    l = sp.add_parser("liste", help="Lister les offres")
    l.add_argument("--statut")
    l.set_defaults(f=cmd_liste)

    t = sp.add_parser("tableau", help="Régénérer le tableau de bord et les pages des offres")
    t.set_defaults(f=cmd_tableau)

    le = sp.add_parser("lettre", help="Générer lettre.pdf depuis lettre.md")
    le.add_argument("id", nargs="?")
    le.add_argument("--toutes", action="store_true", help="tous les dossiers qui ont une lettre.md")
    le.set_defaults(f=cmd_lettre)

    cv = sp.add_parser("cv", help="Générer cv.pdf depuis cv.md (mise en page simple, ou LaTeX s'il est installé)")
    cv.add_argument("id", nargs="?")
    cv.add_argument("--toutes", action="store_true", help="tous les dossiers qui ont un cv.md")
    cv.set_defaults(f=cmd_cv)

    sv = sp.add_parser("serveur", help="Ouvrir le tableau de bord dans le navigateur")
    sv.add_argument("--port", type=int, default=PORT)
    sv.add_argument("--sans-navigateur", action="store_true")
    sv.set_defaults(f=cmd_serveur)

    v = sp.add_parser("verifier", help="Vérifier l'installation et la configuration")
    v.set_defaults(f=cmd_verifier)

    dm = sp.add_parser("demo", help="Découvrir l'outil avec un profil fictif")
    dm.add_argument("--port", type=int, default=8766)
    dm.add_argument("--sans-navigateur", action="store_true")
    dm.add_argument("--sans-serveur", action="store_true", help="générer les pages sans ouvrir le serveur")
    dm.set_defaults(f=cmd_demo)

    args = p.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()
