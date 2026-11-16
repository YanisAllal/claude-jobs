---
description: Lister les candidatures à relancer et préparer les messages de relance
---

Liste les offres au statut `postulee` dont la date de candidature a plus de 7 jours (`./jobs liste --statut postulee`, puis
`suivi.csv` pour les dates), de la plus ancienne à la plus récente, ainsi que les entretiens et tests en cours.

Pour chacune, propose un message de relance court (3 ou 4 phrases, ton simple et direct, rien d'inventé), adapté au canal
(e-mail, LinkedIn de moins de 300 caractères, formulaire). Après 3 semaines sans réponse malgré une relance, propose de passer
l'offre en `sans_reponse`.

Quand la personne confirme une relance, applique `./jobs statut <id> relancee --note "…"`.
