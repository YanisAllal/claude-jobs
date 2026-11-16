# Déroulé du travail (pour Claude)

À lire en début de session, avec `CLAUDE.md` (les règles), puis `journal.md` (ce qui s'est passé avant, propre à la personne).

## La mission en une phrase
Trouver les offres qui collent vraiment au profil, puis tout préparer (note, CV adapté, lettre, réponses de formulaire,
checklist) pour que la personne n'ait plus qu'à relire et cliquer sur « Postuler ». C'est **toi** qui fais en sorte que la
recherche ramène les bonnes offres : ajuste les requêtes toi-même, sans le lui demander.

## Le pipeline complet (`/chercher` puis `/analyser`, ou « recherche complète »)
1. **Collecter**, en parallèle (agents en arrière-plan) :
   - agents `wttj`, `linkedin`, `indeed`, `glassdoor`, `entreprises` (outil Agent, en arrière-plan). Donne-leur la date du
     jour, demande les offres les plus récentes (aujourd'hui, hier, puis la semaine), et cite les requêtes déjà utilisées
     récemment (voir le journal), pour qu'ils en prennent d'autres ;
   - `./jobs chercher` en arrière-plan, si le délai minimum est écoulé (sinon l'outil le dit et s'arrête tout seul ;
     ne touche jamais à `data/etat.json`).
   Si un agent n'est pas reconnu (les définitions ne sont chargées qu'au démarrage d'une session), lance un agent
   `general-purpose` en lui demandant de lire et de suivre `.claude/agents/<nom>.md`.
2. **Analyser** chaque offre `nouvelle` selon le barème de `CLAUDE.md`. Lis vraiment la description : l'expérience demandée
   et le type de contrat sont souvent en bas. Un extrait par expression régulière (« ans », « experience », « stage »,
   « alternance ») aide à repérer vite les éliminatoires.
3. **Ajuster la recherche** : ce qui a mal marché → modifie `recherches`, `mots_cles_titre`, `entreprises_cibles`,
   `entreprises_exclues` dans `preferences.yml`, et note-le dans le journal.
4. **Préparer les dossiers** des offres à 65/100 ou plus, si la personne le demande (3 à 5 par session au plus) : section
   « Prépare le dossier » de `CLAUDE.md`. La personne peut aussi cliquer sur « ✦ Préparer le dossier » dans la page d'une offre.
5. **Récap** : nombre d'offres trouvées et écartées, meilleures pistes avec leur id, points à vérifier avant l'envoi,
   ce que tu as changé dans la recherche.
6. **Journal** : mets à jour `journal.md` (état actuel, une entrée datée dans le journal des recherches).

## Technique : ce qu'il faut savoir
- Toujours passer par `./jobs` (il utilise `.venv`). En cas de dépendances manquantes : `./installer.sh`. Diagnostic : `./jobs verifier`.
- `suivi.csv` est protégé par un verrou (`data/.verrou`) : plusieurs agents peuvent ajouter des offres en même temps.
- `./jobs chercher` fait tourner les requêtes d'un lancement à l'autre (`rotation` dans `data/etat.json`) : mets les plus
  prometteuses en tête de `recherches`. Il écarte d'office les titres contenant un mot négatif et les contrats `internship` d'Indeed.
- `./jobs ajouter` signale quand une offre aurait été filtrée par son titre, mais l'ajoute quand même : c'est voulu, pour les
  offres choisies à la main ou par un agent.
- Si un agent s'arrête sur une **limite d'utilisation** (erreur 429 de l'API), ne le relance pas de zéro : reprends-le avec
  SendMessage une fois la limite levée (son travail est conservé).
- `./jobs serveur` se relance tout seul quand `jobs.py` change. Les modèles HTML et les fichiers des dossiers sont relus à chaque requête.
- **Bouton « ✦ Préparer / Compléter le dossier »** (page d'une offre, via `./jobs serveur`) : lance `claude -p` en arrière-plan
  (`lancer_claude()` dans `jobs.py`, outils limités à la lecture, l'écriture, le web et `./jobs`, 25 min au plus).
  « Compléter » ouvre un champ par `[À COMPLÉTER]` ; les réponses sont intégrées au dossier et, si ce sont des faits, à `cv.md`.
  État et compte rendu : `data/taches/<id>.json` et `.log`.
- **Date limite** : repérée automatiquement dans la description (« date limite … jj/mm/aaaa », « jusqu'au … ») et affichée en
  badge. Écris les dates limites sous cette forme en tête des descriptions que tu ajoutes.
- **Page « Mon profil »** (`/profil` de `./jobs serveur`) : réécrit `preferences.yml` avec `yaml.safe_dump`, ce qui supprime les
  commentaires du fichier. Garde donc les explications importantes dans `journal.md` plutôt qu'en commentaire.
- **CV en PDF** : `./jobs cv <id>` utilise `cv_pdf.py` (LaTeX) si `pdflatex` est installé et `cv.moteur` vaut `auto` ou `latex`,
  sinon `cv_pdf_simple.py` (reportlab). Les deux lisent le même format de `cv.md` et réduisent la mise en page si le CV déborde.

## Ce qu'on a appris (valable pour tout le monde)
- Les requêtes génériques (« data scientist », « comptable ») ramènent surtout des postes expérimentés. Pour un débutant,
  préfère « junior », « jeune diplômé », « débutant » et des intitulés précis.
- **LinkedIn** sature vite (erreur 429 au bout de 3 ou 4 pages lues par un agent) : peu de pages, et jamais deux passages
  le même jour. Sans connexion, ses filtres de date sont ignorés ; les pages de liste publiques
  (`fr.linkedin.com/jobs/<poste>-emplois-<ville>`) affichent l'ancienneté des offres. Les descriptions sont parfois tronquées
  ou traduites : relire l'offre sur le site de l'entreprise.
- **Indeed** et **Glassdoor** bloquent presque toujours la lecture automatique (403) : ils servent au repérage (extraits de la
  recherche web) ; l'offre se lit et se postule sur le site carrières de l'employeur. Indeed classe parfois des stages sous un
  titre neutre : vérifier le contrat.
- **Welcome to the Jungle** : la recherche web ramène beaucoup de pages anciennes ou fermées. Ajoute le mois et l'année à la
  requête, et vérifie que le bouton « Postuler » est présent. Les pages entreprises `app.welcometothejungle.com` sont en
  JavaScript, illisibles : cherche des intitulés précis, une entreprise par recherche.
- **Sites carrières** : beaucoup d'entreprises publient sur des ATS dont les pages publiques (et parfois les flux JSON publics)
  sont lisibles sans compte : Lever (`jobs.lever.co/<entreprise>`), Ashby (`jobs.ashbyhq.com/<entreprise>`), Greenhouse
  (`boards.greenhouse.io/<entreprise>`), Welcome Kit, Teamtailor, SmartRecruiters. Les recherches nominatives
  (« <entreprise> <intitulé exact> ») marchent bien mieux que les génériques.
- **Candidatures spontanées** : un lien vers une page carrières ne suffit pas, il faut le **lien direct du formulaire**. Les pages
  Welcome Kit ont souvent une page cachée `https://<entreprise>.welcomekit.co/jobs/candidatures-spontanees`.
- **Secteur public** : choisirleservicepublic.gouv.fr est lisible avec curl ; France Travail liste beaucoup d'offres de
  partenaires (APEC, HelloWork) dont le texte est sur HelloWork, lisible.
- Les ESN et cabinets de conseil demandent souvent 2 à 3 ans malgré un titre « junior » : vérifier.
