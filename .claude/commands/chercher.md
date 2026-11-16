---
description: Recherche complète d'offres (agents web en parallèle + LinkedIn/Indeed), puis analyse des nouvelles offres
argument-hint: "[sites ou consigne, ex. « seulement WTTJ » ou « data analyst à Lyon »]"
---

Lance une recherche d'offres en suivant `PIPELINE.md` (section « Le pipeline complet ») et les règles de recherche de `CLAUDE.md`.

Consigne éventuelle : $ARGUMENTS

1. Vérifie que l'outil est configuré (`./jobs verifier`). Sinon, propose `/configurer` et arrête-toi.
2. Lis `journal.md` (requêtes et sites utilisés récemment, passages LinkedIn du jour) et `preferences.yml`.
3. Lance **en parallèle et en arrière-plan** les agents `wttj`, `linkedin`, `indeed`, `glassdoor` et `entreprises` (ou seulement
   ceux que demande la consigne). Donne à chacun la date du jour, demande les offres les plus récentes d'abord, et cite les
   requêtes déjà utilisées récemment pour qu'il en prenne d'autres. Si un agent n'est pas reconnu, lance un agent
   `general-purpose` qui lit et suit `.claude/agents/<nom>.md`.
4. En même temps, lance `./jobs chercher` en arrière-plan (il respecte seul son délai minimum ; ne touche jamais à `data/etat.json`).
5. Quand tout est terminé, enchaîne sur l'analyse des nouvelles offres (section « Analyse les nouvelles offres » de `CLAUDE.md`).
6. Termine par le récap (offres trouvées, écartées, 3 à 5 meilleures avec leur id, ajustements de la recherche) et mets à jour
   `journal.md`. Propose de préparer les dossiers des offres à 65 ou plus.
