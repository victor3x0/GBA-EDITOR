# Contribuer

## Ce que tu dois savoir avant d'ouvrir une pull request

Chaque commit doit porter une ligne `Signed-off-by`. Ce n'est pas une formalité :
c'est ce qui garde ouverte une porte qui se referme définitivement au premier
commit accepté sans elle.

**Pourquoi.** Le détenteur des droits peut licencier son propre code comme il
veut — y compris vendre une licence commerciale à une entreprise que la GPL
dérange, ou repasser le moteur sous d'autres termes si le besoin apparaît. Cette
liberté disparaît dès qu'une ligne appartient à quelqu'un d'autre sans qu'on
sache sous quelles conditions elle a été donnée. Le *sign-off* établit cette
traçabilité, contribution par contribution.

C'est aussi la garantie inverse, pour toi : personne ne peut relicencier ta
contribution en dehors des termes que tu as acceptés en la signant.

## Signer un commit

```bash
git commit -s -m "ton message"
```

`-s` ajoute la ligne toute seule. Elle doit porter ton vrai nom et une adresse
valide — un pseudonyme ne certifie rien.

```
Signed-off-by: Prénom Nom <adresse@exemple.org>
```

En l'ajoutant, tu certifies le texte ci-dessous (*Developer Certificate of
Origin* 1.1, le texte utilisé par le noyau Linux et beaucoup d'autres projets) :

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same license (unless I am permitted to submit
    under a different license), as indicated in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

## Sous quelle licence atterrit ta contribution

Cela dépend de l'endroit :

| Où | Licence |
| --- | --- |
| `editor/`, `tools/`, `packaging/` | GPL-3.0-only ([LICENSE](LICENSE)) |
| `runtime/` | zlib ([runtime/LICENSE](runtime/LICENSE)) |

La distinction est structurelle, pas cosmétique : `runtime/` est recopié dans la
ROM de chaque utilisateur. Une contribution GPL qui y atterrirait rendrait tous
les jeux construits avec l'éditeur dérivés de la GPL. Si tu touches à `runtime/`,
tu contribues sous zlib — dis-le explicitement dans la pull request.

## Avant de proposer

Les deux garde-fous du projet tournent en CI, et localement :

```bash
python tools/check_architecture.py --fresh
```

```bash
python -m pytest tests -q
```

Le second saute les tests d'équivalence Python/C sans compilateur C hôte. Pour
les exécuter, désigne-en un :

```bash
CC=/chemin/vers/gcc python -m pytest tests -q
```

[ARCHITECTURE.md](ARCHITECTURE.md) explique comment le code est construit, et
[ROADMAP.md](ROADMAP.md) ce qui est tranché, ce qui est ouvert, et ce qui a été
écarté — avec les raisons. Les lire évite de proposer quelque chose qui a déjà
été décidé dans l'autre sens.
