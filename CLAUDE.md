# claude-jobs — consignes pour Claude

Outil de recherche d'emploi. Les scripts collectent les offres et tiennent le suivi ; **Claude analyse les offres et prépare
les dossiers de candidature**. La personne qui cherche un emploi (nom dans `preferences.yml` → `profil.nom`) envoie elle-même
chaque candidature. Réponds et rédige en français, sauf pour les documents destinés à une offre rédigée en anglais.

**Au début de chaque session**, lis le déroulé du travail (@PIPELINE.md), puis `journal.md` s'il existe (état actuel, décisions
prises, journal des recherches). Mets à jour `journal.md` à la fin de chaque session où quelque chose a changé.

**Si `preferences.yml` ou `cv.md` manquent, ou si `profil.nom` vaut encore « Prénom Nom »**, l'outil n'est pas configuré :
propose de lancer `/configurer` (ou `./jobs serveur` → « Mon profil ») avant toute recherche.

## Fichiers
- `cv.md` : CV de référence. **Seule source de vérité sur le parcours de la personne.** La section « Précisions » peut
  dépasser une page : on y garde tout ce qui peut servir dans une lettre.
- `preferences.yml` : postes visés, expérience, zones, contrats, salaire, critères éliminatoires, requêtes, garde-fous.
- `journal.md` : état actuel, décisions prises avec la personne, journal des recherches. Créé par `./installer.sh`.
- `suivi.csv` : une ligne par offre (séparateur `;`). Ne pas réécrire à la main : passer par `./jobs`.
- `data/offres/<id>.json` : détail de chaque offre, description comprise.
- `candidatures/<id>/` : dossier préparé pour une offre.
- `tableau_de_bord.html` et `pages/<id>.html` : régénérés par chaque commande `./jobs`, à partir de `modele_tableau.html`
  et `modele_offre.html`. Les cases de `checklist.md` doivent rester au format `- [ ]`.
- Tous ces fichiers personnels sont ignorés par git (`.gitignore`) : ne jamais les ajouter à un commit.

## Commandes
```
./jobs verifier                    # état de l'installation et de la configuration
./jobs chercher [--sites linkedin,indeed] [--requete "..."]
./jobs ajouter <url> --titre "..." --entreprise "..." [--lieu ..] [--contrat ..] [--salaire ..] [--source ..] [--description-fichier f.txt]
./jobs noter <id> <score 0-100> --resume "une ligne" [--ecarter]
./jobs statut <id> <statut> [--note "..."] [--action "prochaine étape"]
./jobs liste [--statut nouvelle]
./jobs tableau
./jobs lettre <id> | --toutes      # lettre.md → lettre.pdf
./jobs cv <id> | --toutes          # cv.md → cv.pdf (1 page ; LaTeX si installé, sinon mise en page simple)
./jobs lien <id> [<url>] --canal "..."   # lien direct pour postuler + comment postuler
./jobs serveur                     # tableau de bord sur http://127.0.0.1:8765 (profil, statuts, checklists, bouton « Préparer »)
```
Statuts : nouvelle, a_etudier, ecartee, dossier_pret, postulee, relancee, entretien, test, offre, acceptee, refusee, sans_reponse, expiree.
Contrat : l'écrire sous une forme claire à l'ajout (« CDI », « CDD 12 mois », « Intérim 3 mois », « Freelance »).

## Commandes de Claude Code (`.claude/commands/`)
`/configurer`, `/chercher`, `/analyser`, `/dossier <id>`, `/relances`. Elles reprennent les sections ci-dessous.

## Règles de recherche (ne pas contourner)
- LinkedIn, Indeed et Glassdoor : par `./jobs chercher`, qui applique les limites de `preferences.yml` (peu de requêtes,
  pauses, délai minimum entre deux passages sur un même site). Ne jamais boucler, ne jamais relancer après un blocage,
  ne jamais modifier `data/etat.json` pour passer outre le délai.
- Agents de recherche web (`.claude/agents/`) : `wttj`, `linkedin`, `indeed`, `glassdoor`, `entreprises`. Ils cherchent par la
  recherche web, lisent les pages publiques des offres et les ajoutent au suivi, chacun avec ses propres limites. Ils complètent
  `./jobs chercher` et ne sont pas soumis à son délai. Pour une « recherche complète », les lancer en parallèle.
- Lancer une recherche **seulement quand la personne le demande**.
- **Offres récentes d'abord** : chercher en priorité celles publiées aujourd'hui ou hier, puis dans la semaine ; relever la date
  de publication de chaque offre. Le rappeler à chaque agent, avec la date du jour.
- Jamais de compte connecté de la personne, jamais de candidature soumise à sa place, aucune clé d'API interne d'un site.
- Autres sites : la personne colle le lien ou le texte de l'offre ; l'ajouter avec `./jobs ajouter` (enregistrer la description
  dans `data/tmp/<slug>.txt` puis `--description-fichier`).

## « Analyse les nouvelles offres » (`/analyser`)
Pour chaque offre au statut `nouvelle` (`./jobs liste --statut nouvelle`), lire `data/offres/<id>.json` **en entier**, puis :
1. **Critères éliminatoires** : ceux de `preferences.yml` → `criteres_eliminatoires`, les `entreprises_exclues`, un type de contrat
   absent de `contrat.accepte` (un stage ou une alternance déguisés sous un titre neutre comptent), et l'expérience :
   **Règle d'expérience** : l'expérience de la personne est `experience.annees` (hors stages et alternance), décrite par
   `experience.resume`. Lire la description en entier (profil, champs « expérience », « niveau requis », souvent en bas).
   Écarter toute offre qui exige plus que `annees + ecart_tolere_annees`, ou une expérience précise indispensable absente de
   `cv.md`, ou un diplôme que la personne n'a pas. Si l'écart est d'au plus un an, ou si l'expérience précise est seulement
   « souhaitée » : ne pas écarter, mais retirer 15 à 20 points et écrire le point faible en tête du résumé.
   Si l'un s'applique : `./jobs noter <id> <score> --ecarter --resume "Écartée : <raison>"`.
2. Sinon, **noter sur 100** :
   - adéquation des compétences et des missions avec `cv.md` et `postes_vises` : 40
   - niveau d'expérience compatible (règle ci-dessus) : 20
   - secteur ou thème dans `secteurs_preferes` : 15
   - contrat (`contrat.prefere` > autres contrats acceptés), lieu (`localisation`), salaire (`salaire`) : 15
   - qualité de l'offre (missions claires, entreprise identifiable, date récente) : 10
3. `./jobs noter <id> <score> --resume "<pourquoi en une ligne, points forts et points faibles>"`.
4. **Améliorer la recherche est le travail de Claude, pas celui de la personne.** Après chaque analyse, regarder ce qui ressort
   mal (trop de postes trop expérimentés, titres hors sujet, stages déguisés, secteurs exclus) et modifier soi-même `recherches`,
   `mots_cles_titre`, `entreprises_cibles` et `entreprises_exclues` dans `preferences.yml`. Ne jamais lui demander de le faire.
   Les requêtes sont utilisées à tour de rôle, 2 par lancement : mettre les plus prometteuses en tête. Noter le changement dans `journal.md`.
5. Finir par un récap court : les 3 à 5 meilleures offres (avec leur id), et ce qui a été ajusté dans la recherche.
Si la description est vide, le dire et noter seulement à partir du titre et de l'entreprise, avec prudence.

## « Prépare le dossier <id> » (`/dossier <id>`)
Créer `candidatures/<id>/` avec :
- `fiche.md` : poste, entreprise, lien, contrat, lieu, salaire ; ce que l'entreprise fait (sans inventer : marquer
  « à vérifier » ce qui n'est pas dans l'offre) ; correspondances CV ↔ offre ; écarts et comment les présenter ;
  mots-clés de l'offre (que Claude intègre lui-même au CV et à la lettre) ; 3 questions à poser en entretien.
- `cv.md` : CV adapté à l'offre, **`cv.max_pages` page(s)** (1 par défaut), dans la langue de l'offre. Réordonner et reformuler pour
  mettre en avant ce qui compte pour ce poste, reprendre les mots-clés de l'offre. **Ne jamais inventer** d'expérience, de
  compétence, de chiffre ou de diplôme absents de `cv.md`. Garder le format du `cv.md` de référence :
  `# Prénom Nom`, `**Accroche**`, ligne de coordonnées séparées par ` · `, sections `## …`, puis
  `**Entreprise — Intitulé** · Lieu · dates` suivi de puces `- `, et `- **École** — Diplôme · dates` pour la formation, ligne en
  retrait de 2 espaces pour les cours. Puis `./jobs cv <id>` génère `cv.pdf`. S'il dépasse la limite, raccourcir `cv.md`.
- `lettre.md` : lettre courte (150 à 250 mots). Première ligne `Objet : …` (lettre en anglais : `Subject: …`), puis des paragraphes
  séparés par une ligne vide (« Madame, Monsieur, », le corps, une formule finale courte). **Pas de signature** à la fin : la mise
  en page signe déjà à droite. Puis `./jobs lettre <id>` génère `lettre.pdf` (coordonnées de `profil`, date, objet, signature).
- `reponses.md` : réponses prêtes à copier pour les champs habituels des formulaires, une section `## …` par champ :
  motivation (3 à 5 phrases), présentation (2 ou 3 phrases), prétentions salariales cohérentes avec `salaire`, disponibilité,
  message LinkedIn de moins de 300 caractères (titre de section contenant « LinkedIn »). Une ligne `*(…)*` est une note pour la
  personne, exclue du bouton « Copier ».
- `checklist.md` : étapes pour postuler (lien direct, pièces à joindre, champs à remplir) et date de relance (J+7), en cases `- [ ]`.
- **Ne jamais mentir, ni dans la lettre, ni dans le CV, ni dans les réponses.** Chaque phrase doit venir de `cv.md` ou de
  l'offre. Interdit : ce que la personne aurait « appris », « aimé » ou « retenu », des tâches ou des cours supposés, une
  disponibilité supposée. La motivation s'appuie sur l'offre (« vos sujets X correspondent à mon expérience en Y »). Si une
  information manque, écrire `[À COMPLÉTER : …]` : la page de l'offre les compte et le bouton « ✦ Compléter le dossier » ouvre
  un champ par question.
- **Ton** : simple, direct, naturel, comme une personne qui écrit à un recruteur. Phrases courtes et concrètes. Bannir les
  formules solennelles (« Je vous prie d'agréer… », « a retenu toute mon attention »), les accroches lyriques et les superlatifs.
  Dans un champ de formulaire, un « Bonjour » et un « Merci, <prénom> » suffisent.

Puis `./jobs lien <id> <lien du formulaire> --canal "comment postuler, en une phrase"` (obligatoire si le lien de l'offre n'est
pas celui où l'on postule, et toujours pour une candidature spontanée : vérifier que le lien mène bien à un formulaire),
puis `./jobs statut <id> dossier_pret --action "Relire le dossier puis postuler"`. Signaler tout point à vérifier avant l'envoi.

## Suivi
Quand la personne annonce un changement (« j'ai postulé chez X », « refus de Y », « entretien jeudi avec Z »), retrouver
l'offre avec `./jobs liste` et appliquer `./jobs statut` avec une `--note` et, si utile, une `--action`.
« Quoi relancer ? » (`/relances`) : offres `postulee` dont la date de candidature a plus de 7 jours.
Quand la personne donne une consigne durable (« pas d'intérim », « Lyon seulement »), l'appliquer dans `preferences.yml`
et la noter dans la section « Décisions prises » de `journal.md`.
