# Écrire un script

Ce document s'adresse à qui **écrit** un script dans l'éditeur. Il répond à une seule
question, mais complètement : *qu'est-ce que je peux écrire en Lua ici, et qu'est-ce qui ne
marchera pas ?*

| Fichier | Pour qui |
| --- | --- |
| [README](README.md) | un visiteur |
| [ROADMAP](ROADMAP.md) | qui décide de la suite |
| [ARCHITECTURE](ARCHITECTURE.md) | qui modifie l'éditeur |
| **ce fichier** | qui écrit un script |

---

## Le principe, en une phrase

**Votre script n'est pas exécuté : il est traduit en C, puis compilé dans la ROM.**

Il n'y a pas d'interpréteur Lua dans la cartouche — pas de machine virtuelle, pas de
ramasse-miettes, pas d'allocation. Ce que vous écrivez devient des fonctions C, et tourne à
la vitesse du C.

C'est ce qui rend le jeu rapide, et c'est ce qui explique **tout** ce document : Lua fournit
ici la *syntaxe*, pas sa bibliothèque ni son modèle d'exécution. Le sous-ensemble accepté est
celui qui se traduit sans rien inventer à l'exécution.

Une règle de pouce qui vous évitera la plupart des surprises :

> Tout ce qui doit être connu au moment de jouer est connu **au moment de compiler**. La
> taille d'un tableau, le nom d'une animation, la valeur de `#t` : tout ça est décidé avant
> que la ROM existe.

Quand vous écrivez quelque chose qui sort du sous-ensemble, **l'éditeur vous le dit** au
Build, avec la ligne et ce qu'il faut écrire à la place. Aucun refus n'est silencieux.

---

## Ce que vous pouvez écrire

Le vocabulaire complet. Ce qui n'est pas dans cette section n'existe pas.

### Structure d'un script

Un script ne contient que des **handlers d'événement** et des variables :

```lua
local vitesse = 2              -- l'état du script, conservé d'une frame à l'autre

function on_start()            -- appelé une fois
    self:play_anim("idle")
end

function on_update()           -- appelé à chaque frame
    self.position = self.position + vec2(vitesse, 0)
end
```

Les handlers disponibles dépendent du type de script (acteur, scène, caméra) et sont listés
dans le panneau **Events** du Script Editor. Un nom qui n'en est pas un est refusé : le
moteur n'appellerait jamais cette fonction.

### Contrôle

```lua
if x > 0 then … elseif x < 0 then … else … end
while x > 0 do … end
for i = 1, 10 do … end
for i = 10, 1, -1 do … end     -- le pas s'écrit en clair : c'est lui qui dit le sens
break
return
```

### Valeurs

| Type | Écriture | Notes |
| --- | --- | --- |
| Entier | `12`, `-3` | **le seul type numérique** — pas de virgule flottante |
| Booléen | `true`, `false` | vaut 1 / 0 dans le C émis |
| `nil` | `nil` | vaut 0 |
| Vecteur | `vec2(x, y)`, `vec3(x, y, z)` | `+`, `-`, et `*` par un entier |
| Rectangle | `rect(x, y, w, h)` | pour les bornes (caméra, zones) |
| Tableau | `{1, 2, 4, 8}` ou `array(20, 12)` | taille fixe, **entiers uniquement**, indexé à partir de 1 |
| Chaîne | `"walk"`, `"Arena"` | un **nom cité du projet**, pas un texte à afficher |

Deux points valent d'être soulignés, parce qu'ils surprennent :

- **La division est entière.** `7 / 2` vaut `3`. Il n'y a pas de nombre à virgule dans le
  moteur — ni ici, ni dans les composants, ni dans la ROM.
- **Une chaîne n'est pas du texte.** Les guillemets servent à **nommer** quelque chose du
  projet : une animation, une scène, une palette, une clé de texte. Le texte que le joueur
  lit vit dans la **table de textes**, avec sa mise en forme et ses traductions, et s'affiche
  par `text.draw`.

### Opérateurs

```lua
+   -   *   /   %          -- arithmétique, entière
==  ~=  <   <=  >   >=     -- comparaison
and or  not                -- logique
#t                         -- taille d'un tableau (calculée au build)
```

### Appels

```lua
self:play_anim("walk")             -- une MÉTHODE d'acteur : deux points
self.position = vec2(10, 20)       -- une PROPRIÉTÉ : un champ, pas un appel
sfx.play("Bip")                    -- une fonction du moteur
local IA = require("behaviors/ia") -- un behavior partagé
IA.update(self)
```

Le catalogue complet des fonctions et propriétés du moteur est dans le panneau **API** du
Script Editor, avec la description de chaque argument. Il n'est pas repris ici : il évolue à
chaque version, et l'éditeur le tient à jour tout seul.

### Séquences — attendre, en ligne droite

Un handler rend la main à chaque frame : pour enchaîner « avance, puis attends, puis parle »,
il faudrait une machine à états écrite à la main. Une **séquence** l'écrit en ligne droite et
la machine à états est produite au build.

```lua
function on_sequence_intro()
    self:move_to(vec2(120, 80), 60)
    wait_until(self.position.x >= 120)   -- attend que ce soit vrai
    wait(30)                             -- attend 30 frames
    text.draw_in("bulle", "garde_01")
    scene.switch("Arena")
end

function on_start()
    sequence.start("intro")
end
```

Une séquence est une fonction de premier niveau nommée `on_sequence_<nom>`. On la pilote par
`sequence.start(nom)`, `sequence.stop(nom)` et `sequence.running(nom)` — le nom étant celui
qui suit `on_sequence_`. Plusieurs séquences peuvent tourner en même temps ; elles avancent
dans l'ordre où elles sont écrites, à la fin de `on_update`.

Cinq choses à savoir, et une seule surprend :

- **Une séquence s'arrête toute seule** à sa dernière ligne. Écrire `sequence.stop` sur soi à
  la fin est inutile.
- **Une variable locale survit à l'attente.** `local depart = self.position.x` écrit avant un
  `wait` se relit après, contrairement à ce qui se passerait dans un handler ordinaire.
- **`wait_until` réévalue sa condition à chaque frame.** *C'est le seul endroit du langage où
  un argument n'est pas évalué une fois à l'appel.* En Lua, `wait_until(x >= 120)` calculerait
  `x >= 120` immédiatement et passerait `true` ou `false` ; ici, l'expression est réévaluée
  tant qu'elle est fausse. Écart assumé : sans lui, `wait_until` n'attendrait rien.
- **Une attente s'écrit seule sur sa ligne, au premier niveau d'une séquence** — pas dans un
  `if`, pas dans une boucle, pas dans un autre handler. C'est la ligne droite qui permet le
  découpage. Pour attendre sous condition, mettez la condition **dans** l'attente, ou
  déclarez une deuxième séquence et démarrez-la depuis le `if`.
- **Une condition qui ne peut jamais devenir vraie est refusée au Build.** `wait_until(false)`,
  ou une condition qui ne lit que des variables qu'aucune ligne du script n'assigne : la
  séquence resterait bloquée là sans que rien ne le dise en jeu.

Chaque attente coûte une frame de plus qu'une exécution en ligne droite — invisible sur une
cinématique, à savoir si vous comptez les frames.

---

## Ce qui n'existe pas, et quoi écrire à la place

Tout ce qui suit est **refusé au Build**, avec un message qui dit la même chose que cette
section. Rien n'est ignoré en silence.

### Boucles et sauts

| Vous écrivez | Pourquoi non | À la place |
| --- | --- | --- |
| `for k, v in pairs(t) do … end` | un itérateur suppose des tables Lua, que le moteur n'a pas | `for i = 1, #t do` |
| `repeat … until c` | la seule boucle à condition est `while`, testée en tête | `while true do … if c then break end end` |
| `goto etiquette` | pas de saut | `break`, `return`, ou un `if` |
| `::etiquette::` | pas de saut, donc pas d'étiquette | — |
| `do … end` | un bloc nu n'ouvre qu'une portée, et une variable vit dans sa fonction | écrivez son contenu directement |

### Fonctions

**Un script ne déclare pas ses propres fonctions.** Les fonctions de premier niveau sont les
handlers d'événement et les séquences (`on_sequence_<nom>`) ; le code partagé entre plusieurs
acteurs vit dans un **behavior** — un fichier de `scripts/behaviors/`, importé par
`require("behaviors/nom")` et inliné au build.

| Vous écrivez | À la place |
| --- | --- |
| `local function f() … end` | un behavior |
| `function f() … end, dans un corps` | un behavior |
| `function objet:methode() … end` | un behavior (les méthodes existantes sont celles des acteurs) |
| `local f = function() … end` | rien : une fonction n'est pas une valeur, il n'y a ni rappel ni fermeture |
| `...` | rien : sans fonction déclarée, rien n'a d'arguments variables |

### Texte et chaînes

| Vous écrivez | Pourquoi non | À la place |
| --- | --- | --- |
| `a .. b` | pas de chaîne manipulable : composer du texte demanderait un tampon et une allocation | un marqueur de valeur dans l'entrée de texte : `« Score : $mon_global »`, puis `text.draw` |

C'est la question la plus fréquente, alors voici la réponse complète. Pour afficher
« Score : 12 » :

1. dans l'écran **Texte**, créez une entrée dont le contenu est `Score : $score_joueur` ;
2. dans le script, mettez la valeur à jour : `global.set("score_joueur", 12)` ;
3. affichez l'entrée : `text.draw(2, 2, "score")`.

La valeur est substituée à l'affichage. Le texte reste traduisible, et le script n'a jamais
manipulé une seule chaîne.

### Arithmétique

| Vous écrivez | Pourquoi non | À la place |
| --- | --- | --- |
| `a ^ b` | pas de flottant, pas de fonction puissance | `x * x` |
| `a // b` | `/` est **déjà** une division entière | `a / b` |

Les opérateurs binaires ne sont pas non plus dans le sous-ensemble : `a & b`, `a | b`,
`a ~ b`, `a << b`, `a >> b`, `~a`. Un drapeau se range dans une variable globale, un décalage
se fait en multipliant ou en divisant, et les registres du matériel se pilotent par l'API
(`layer`, `window`, `blend`). Attention à un piège de lecture : `~=` (différent de) existe
bien — c'est `~` **seul** qui n'existe pas.

### La bibliothèque standard de Lua

Elle n'existe pas. Aucun de ces modules n'est embarqué dans la ROM :

| Vous écrivez | Pourquoi non | À la place |
| --- | --- | --- |
| `string.format(…)` | pas de chaîne manipulable | la table de textes et son balisage |
| `table.insert(t, v)` | un tableau a une taille fixe, décidée au build | `array(n)`, et un compteur si le contenu varie |
| `os.time()` | pas d'horloge système | `scene.frame` compte les frames |
| `io.open(…)` | pas de système de fichiers | `save.write` / `save.read` (SRAM) |
| `coroutine.create(f)` | le moteur appelle `on_update` et reprend la main | un état dans une variable, et le `if` qui le lit |
| `debug.traceback()` | il n'y a pas de machine virtuelle à inspecter | — |
| `utf8.char(…)` | l'encodage est décidé au build | — |
| `package.path` | rien n'est chargé à l'exécution | `require("behaviors/nom")` |

Et les fonctions globales :

| Vous écrivez | Pourquoi non | À la place |
| --- | --- | --- |
| `print(x)` | la GBA n'a pas de console | `text.draw` pour le joueur ; une trace de développement n'existe pas encore (v0.14) |
| `pairs(t)` / `ipairs(t)` / `next(t)` | pas de table à parcourir | `for i = 1, #t do` |
| `type(x)` | le type est connu au build, jamais à l'exécution | — |
| `tostring(x)` | pas de chaîne manipulable | un marqueur de valeur dans le texte |
| `tonumber(s)` | il n'y a pas de chaîne à convertir | — |
| `pcall(f)` / `xpcall(f, h)` | pas d'exception : le C n'a ni pile de déroulement ni gestionnaire | un `if` |
| `error(msg)` / `assert(c)` | pas d'exception, pas de console | un `if` qui corrige la valeur |
| `setmetatable(t, mt)` / `getmetatable(t)` | pas de métatable, faute de table | — |
| `rawget(t, k)` / `rawset(t, k, v)` / `rawequal(a, b)` / `rawlen(t)` | idem | `#t` pour la taille |
| `select(n, ...)` / `unpack(t)` | pas d'appel à arité variable | — |
| `collectgarbage()` | rien n'est alloué à l'exécution | — |
| `load(src)` / `loadstring(src)` / `dofile(chemin)` / `loadfile(chemin)` | on ne charge pas de code dans une ROM | `require("behaviors/nom")`, résolu au build |

### `math` — le faux ami

Il existe un module `math`, **mais ce n'est pas celui de Lua**. C'est celui du moteur, en
entiers, et il offre exactement ceci :

```
abs   atan2   clamp   cos   ease   lerp   max   min   rand   sign   sin   sqrt
```

Trois différences à retenir :

- `math.sin` et `math.cos` prennent des **degrés**, pas des radians ;
- le tirage aléatoire s'appelle `math.rand(lo, hi)` ;
- il n'y a **pas** d'arrondi, parce qu'il n'y a rien à arrondir.

| Vous écrivez | À la place |
| --- | --- |
| `math.floor(x)` | rien : tout est entier, `/` tronque déjà |
| `math.ceil(x)` | `(a + b - 1) / b` pour arrondir une division au-dessus |
| `math.random(a, b)` | `math.rand(lo, hi)` |
| `math.randomseed(n)` | rien : la graine n'est pas exposée |
| `math.pi` | rien : les angles sont en degrés |
| `math.huge` | une borne écrite en clair |
| `math.pow(x, n)` | `x * x` |
| `math.fmod(a, b)` | `a % b` |
| `math.modf(x)` | rien : pas de partie fractionnaire |

---

## Où les erreurs apparaissent

Au **Build**. Le panneau de log affiche chaque refus avec son message, et la ligne quand elle
est connue :

```
[error] Ball.lua — ligne 12 : `repeat … until` n'existe pas : la seule boucle à
        condition est `while`, testée en tête. …
```

Une **erreur** arrête le build : le C émis serait faux ou vide. Un **avertissement** le
laisse continuer : ce que vous avez écrit compile, mais ne fera probablement pas ce que vous
croyez (un sfx qui n'existe pas, une valeur hors de la plage d'une variable typée).

Le script n'est pas vérifié pendant que vous tapez — seulement au Build.

---

## Pourquoi ces limites, plutôt qu'un « vrai » Lua

Embarquer un interpréteur coûterait la mémoire et le temps processeur qui font justement la
différence entre un jeu fluide et un jeu qui rame sur du matériel de 2001 : 16,8 MHz, 32 Ko
de mémoire rapide, aucune unité de calcul flottant. Chaque limite de ce document est le
revers d'une garantie :

| La limite | Ce qu'elle achète |
| --- | --- |
| Pas de table, pas de closure, pas de coroutine | aucune allocation à l'exécution — la mémoire est décidée au build, donc mesurable |
| Que des entiers | aucune émulation flottante, qui coûterait des centaines de cycles par opération |
| Taille des tableaux connue au build | pas de vérification de bornes à l'exécution |
| Noms résolus au build | `sfx.play("Bip")` devient un index, pas une recherche par chaîne |

Le sous-ensemble s'étend au fil des versions, et toujours pour la même raison : un cas réel
l'a demandé. Les tableaux, les vecteurs et les propriétés sont arrivés comme ça. Ce qui n'est
pas dans ce document ne manque à personne pour l'instant — si quelque chose vous manque, la
[ROADMAP](ROADMAP.md) est l'endroit où ça se discute.
