# Pipeline de rendu des polices

Une zone de texte référence une **FontAsset**. Une FontAsset est une recette :
elle choisit une chaîne de sources (et donc les replis), une taille, une
hauteur de ligne et un mode de rasterisation. Une `Font` dans
`assets/fonts/` reste une source ; elle ne représente pas le choix typographique
fait par la zone.

## Une seule matérialisation

Au build comme dans le canvas, la recette est matérialisée en glyphes temporaires :

```text
Texte + balises → FontAsset → RasterGlyphs → composition pixels → tuiles GBA → VRAM
```

`RasterGlyph` porte les métriques, la couverture, et — pour une source bitmap —
la couleur RGB de chaque pixel. Cette dernière donnée est importante : une
planche bitmap ne doit jamais être réduite à un simple masque opaque.

## Palette et encre

- Une source **bitmap** conserve ses couleurs. Elles deviennent les indices 1 à
  15 de la palette de police ; l'index 0 reste transparent.
- Une source **vectorielle** n'a pas de couleurs source. En mode `binary` ou
  `dither`, elle produit transparence + noir à l'index 1. En mode `coverage`,
  elle produit une rampe de gris sur les indices 1 à 15.
- Une zone de texte lit une seule banque de palette. Son encre choisie remappe
  les pixels non transparents vers l'index demandé lors de la composition.
  Une zone fille d'un conteneur lit la banque de ce conteneur ; une zone libre
  lit la banque attribuée à sa police dans la scène.
- Le remplacement linguistique de la police par défaut conserve ce même choix
  de banque : il ne crée pas une seconde palette logique.

## Règle de parité éditeur / ROM

Le canvas ne lit pas directement une planche lorsqu'une FontAsset est active :
il peint les mêmes `RasterGlyphs` que le build. Les anciennes `Font` sans
FontAsset conservent, elles, le chemin historique de planche PNG/BMFont.

Cela garantit que la couverture d'un caractère, son dépôt dans la ligne, son
index de palette et son comportement de repli sont les mêmes dans le canvas,
l'aperçu typographique et la ROM.
