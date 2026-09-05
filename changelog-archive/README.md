# Archive du changelog

Le détail complet de chaque entrée du [CHANGELOG](../CHANGELOG.md) : le pourquoi, les
décisions verrouillées, les pièges rencontrés, les mesures — extrait de la roadmap au moment
où chaque version a été livrée, pour que ni l'un ni l'autre ne devienne illisible.

Un fichier par version — et un par [chantier technique](../ROADMAP.md#chantiers-techniques)
refermé, référencé par son nom plutôt que par un numéro : un chantier technique ne touche ni le
CHANGELOG ni le README, mais sa discussion se range ici comme les autres. Rien n'est perdu :
c'est ici qu'on vient rouvrir une décision passée avec le contexte complet qui l'a motivée,
plutôt que de la retrancher à l'aveugle.

Pour un résumé court, voir le [CHANGELOG](../CHANGELOG.md). Pour ce qui reste à faire, voir
[ROADMAP.md](../ROADMAP.md).

| Version | Sujet |
| --- | --- |
| [v0.2](v0.2.md) | Gestion des palettes de couleurs |
| [v0.3](v0.3.md) | Background vivant, texte et interface in-game |
| [v0.4](v0.4.md) | Animation de décor |
| [v0.5](v0.5.md) | Sauvegarde (SRAM) |
| [v0.6](v0.6.md) | Polish de la boucle de jeu |
| [v0.7](v0.7.md) | Structures de données |
| [v0.8](v0.8.md) | Son : la musique par scène, les transitions, le mixage |
| [v0.9](v0.9.md) | Traduction des jeux créés avec l'éditeur (phases 1 à 4, EN COURS) |
| [v0.14](v0.14.md) | Diagnostic — ce que le jeu fait, et ce qu'il coûte |
| [v0.15](v0.15.md) | Visibilité des éléments d'interface |
| [v0.19](v0.19.md) | Le sous-pixel |
| [v0.20](v0.20.md) | L'état du monde : les collections persistantes |
| [v0.21](v0.21.md) | Le texte adressable : le dialogue piloté par la donnée |
| [v0.23](v0.23.md) | Ce qu'un boss demande |
| [v0.25](v0.25.md) | L'interface possède son chemin matériel |

### Chantiers techniques

| Chantier | Sujet |
| --- | --- |
| [`global.nom` / `const.nom`](global-const.md) | L'accès pointé remplace les accesseurs |
| [L'identité d'un asset et son fichier](asset-identity.md) | Le nom de fichier fait foi, et un renommage n'est pas une suppression |
| [Les formats acceptés à l'import](import-formats.md) | `.png` pour les images, `.fnt` en plus pour les polices — rien d'autre |
