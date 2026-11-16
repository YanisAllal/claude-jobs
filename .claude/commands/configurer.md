---
description: Configurer ton profil (CV, postes visés, lieux, contrats, salaire) en répondant à quelques questions
argument-hint: "[chemin de ton CV en PDF, Word ou texte]"
---

Tu accueilles une personne qui découvre claude-jobs. Ton but : remplir `preferences.yml` et `cv.md` avec elle, en quelques
minutes, sans jargon. Sois chaleureux et bref. Tutoie-la.

## 1. Vérifier l'installation
Lance `./jobs verifier`. Si les dépendances Python manquent, lance `./installer.sh` (avec son accord) puis revérifie.
Si `preferences.yml` existe et que le profil est déjà rempli, demande si elle veut tout reprendre ou seulement modifier
certains points ; dans ce cas, ne pose que les questions utiles.

## 2. Le CV
Argument éventuel : $ARGUMENTS
- Si un chemin de CV est donné, lis-le (PDF : outil Read ; Word : `textutil -convert txt` sur macOS ou `pandoc` s'il est
  installé ; sinon demande un PDF ou le texte).
- Sinon, demande-lui de glisser son CV (PDF) dans la conversation, ou de coller son texte, ou de donner son profil LinkedIn
  en texte.
- Écris `cv.md` au format décrit dans `exemples/cv.exemple.md` (nom, accroche, coordonnées, sections, entrées
  `**Entreprise — Intitulé** · Lieu · dates`, puces). **Recopie fidèlement : n'invente rien, ne reformule pas les chiffres.**
- Pose ensuite 2 ou 3 questions pour enrichir la section « Précisions » (projets non listés, outils, résultats chiffrés,
  langues et niveau, mobilité, date de disponibilité). Dis-lui que tout ce qu'elle ajoute là peut servir dans les lettres, et
  que rien d'autre ne sera inventé.

## 3. Les préférences
Pose les questions **par petits groupes** avec l'outil AskUserQuestion quand les choix sont fermés (contrats, niveau,
télétravail, langues), et en texte libre sinon. Propose des réponses déduites du CV (« D'après ton CV, tu vises plutôt
contrôleur de gestion junior ? »). Questions à couvrir :
1. Postes visés (2 à 5 intitulés) et secteurs préférés.
2. Niveau et années d'expérience hors stages ; écart toléré (1 an par défaut).
3. Contrats acceptés et préféré ; salaire minimum et visé (brut annuel) ; si elle ne sait pas, propose une fourchette
   prudente et dis d'où elle vient (ou laisse vide).
4. Où : ville de recherche, villes et zones acceptées (propose les communes voisines), télétravail complet accepté ?
5. Ce qu'elle refuse : secteurs, types de poste, entreprises.
6. Langues des candidatures (français, anglais).
7. Des entreprises qu'elle aimerait particulièrement rejoindre ?

## 4. Écrire la configuration
- Pars de `exemples/preferences.exemple.yml` (ou du `preferences.yml` existant) et remplis-le en gardant ses commentaires.
- **Déduis toi-même** les réglages de recherche, sans les lui demander :
  - `recherches` : 6 à 10 requêtes courtes, des plus précises aux plus larges (« <poste> junior », « <poste> débutant »,
    variantes d'intitulés, anglais si pertinent) ;
  - `mots_cles_titre.positifs` : les mots-clés des intitulés visés et de leurs variantes (vide si les intitulés sont très
    variés) ; `negatifs` : adapte la liste d'exemple au niveau (garde « senior », « lead » pour un débutant ; retire « senior »
    pour une personne confirmée ; retire « stage » ou « alternance » si elle en cherche un) ;
  - `localisation.zones_acceptees` : la ville, les communes voisines, le département et la région ;
  - `entreprises_cibles` : celles qu'elle a citées, plus 5 à 10 employeurs connus du secteur et de la ville (dis-lui
    lesquels tu as ajoutés) ;
  - `cv.moteur` : `auto`.
- Copie `exemples/journal.exemple.md` en `journal.md` s'il n'existe pas, et note dans « Décisions prises » ce qu'elle a dit
  (avec la date du jour).
- Lance `./jobs verifier` puis `./jobs tableau`.

## 5. Conclure
Résume en 5 lignes ce que tu as compris (postes, lieux, contrats, salaire, exclusions) et demande si c'est juste.
Puis explique la suite en 3 étapes :
1. `./jobs serveur` dans un terminal pour ouvrir le tableau de bord (page « Mon profil » pour tout modifier) ;
2. `/chercher` pour lancer une première recherche, puis `/analyser` pour noter les offres ;
3. sur la page d'une offre, « ✦ Préparer le dossier » (ou `/dossier <id>`) : CV adapté, lettre, réponses, checklist.
Rappelle que rien n'est jamais envoyé à sa place.
