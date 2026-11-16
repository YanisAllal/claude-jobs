---
description: Préparer le dossier de candidature d'une offre (fiche, CV adapté, lettre, réponses, checklist)
argument-hint: "<id de l'offre> (ou plusieurs, séparés par des espaces)"
---

Prépare le dossier de candidature de : $ARGUMENTS

Si aucun id n'est donné, liste les offres à 65 ou plus sans dossier (`./jobs liste`) et demande lesquelles préparer.
Pour chaque id, suis exactement la section « Prépare le dossier » de `CLAUDE.md` : relis la page de l'offre si la description
est résumée, crée `candidatures/<id>/` (fiche, cv.md, lettre.md, reponses.md, checklist.md), lance `./jobs cv <id>` et
`./jobs lettre <id>`, enregistre le lien direct pour postuler avec `./jobs lien`, puis passe le statut à `dossier_pret`.

**Rien d'inventé** : chaque phrase vient de `cv.md` ou de l'offre ; sinon `[À COMPLÉTER : …]`.
Termine en listant les `[À COMPLÉTER]` restants et les points à vérifier avant l'envoi, et rappelle que la page de l'offre
(`./jobs serveur`) permet de cocher la checklist, copier les réponses et modifier la lettre.
