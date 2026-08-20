-- Réaction visuelle : pop, squash et stretch écrivent tous self.sprite_scale,
-- un seul peut donc jouer à la fois — d'où un compteur unique et le genre en
-- cours. FX_NONE rend la main à l'étirement continu lié à la vitesse, en bas
-- de on_update. Ball est un prefab poolé : `fx` et `fx_t` sont écrits par le
-- script, ils ont donc une copie par instance ; les quatre FX_* ne le sont
-- jamais, ils restent partagés. La balle a « Affine transform » coché — sans
-- ce slot de matrice, rotation et helpers d'échelle n'auraient nulle part où
-- écrire.
local FX_NONE    = 0   -- rien en cours : l'étirement suit juste la vitesse
local FX_POP     = 1   -- apparition : la balle grossit depuis rien
local FX_SQUASH  = 2   -- mur haut/bas : elle s'aplatit dans le sens du choc
local FX_STRETCH = 3   -- raquette : le choc vient du côté, elle s'allonge
local fx   = FX_POP
local fx_t = 0

function on_start()
    local vx = 2
    if math.rand(0, 1) == 0 then
        vx = -2
    end
    -- self.velocity est en Q8 depuis la ROADMAP v0.19 (256 = 1 px/frame) :
    -- les vitesses de ce script restent des pas entiers de pixels, donc ×256
    -- ici suffit — aucun sous-pixel n'est demandé, seule l'unité a changé.
    self.velocity = vec2(vx * 256, 256)
    self.rotation = math.atan2(1, vx)   -- un angle : l'échelle des composantes n'y change rien
    fx   = FX_POP
    fx_t = 0
end

function on_update()
    local pos = self.position

    -- self:apply_velocity() remplace `self.position = self.position +
    -- self.velocity` (ROADMAP v0.19) : les deux membres n'ont plus la même
    -- échelle depuis que self.velocity est Q8. `n` rejoue le rôle de
    -- l'ancien `pos + vel` — la position candidate, testée avant d'être
    -- éventuellement corrigée par un rebond.
    self:apply_velocity()
    local n = self.position
    local vel = self.velocity

    -- Rebond vertical sur tiles solides
    if vel.y < 0 then
        if tile.get(n.x, n.y) ~= 0 or tile.get(n.x + 7, n.y) ~= 0 then
            self.velocity = vec2(vel.x, -vel.y)
            self.position = vec2(n.x, pos.y)   -- annule le déplacement Y de cette frame
            n   = self.position
            vel = self.velocity
            sfx.play("WALLBOUNCE")
            fx   = FX_SQUASH
            fx_t = 0
        end
    end
    if vel.y > 0 then
        if tile.get(n.x, n.y + 7) ~= 0 or tile.get(n.x + 7, n.y + 7) ~= 0 then
            self.velocity = vec2(vel.x, -vel.y)
            self.position = vec2(n.x, pos.y)
            n   = self.position
            vel = self.velocity
            sfx.play("WALLBOUNCE")
            fx   = FX_SQUASH
            fx_t = 0
        end
    end

    -- Sortie de terrain : la balle ne fait que signaler le camp qui encaisse
    -- (point_side) puis se détruit — la scène PONG gère score/victoire/spawn.
    if n.x < 0 then
        global.set("point_side", 1)
        self:destroy()
        return
    end
    if n.x > 240 then
        global.set("point_side", 0)
        self:destroy()
        return
    end

    global.set("ball_y", n.y)

    -- Orientation : le sprite pointe dans le sens du déplacement — l'axe
    -- local que squash/stretch étirent (self.sprite_scale.x) tourne avec lui.
    self.rotation = math.atan2(vel.y, vel.x)

    -- L'effet d'impact prime ; une fois retombé, l'étirement suit la vitesse
    -- en continu.
    if fx ~= FX_NONE then
        fx_t = fx_t + 1
        if fx == FX_POP then
            self:pop(fx_t, 14, 40)
            if fx_t >= 14 then fx = FX_NONE end
        elseif fx == FX_SQUASH then
            self:squash(fx_t, 9, 35)
            if fx_t >= 9 then fx = FX_NONE end
        elseif fx == FX_STRETCH then
            self:stretch(fx_t, 10, 45)
            if fx_t >= 10 then fx = FX_NONE end
        end
    else
        -- vitesse ×100 (×10000 sous la racine pour garder 2 décimales de
        -- précision — math.sqrt est entier, pas de virgule flottante sur
        -- GBA). vel est Q8 (ROADMAP v0.19) : /256 ramène chaque composante en
        -- pixels/frame AVANT le carré, pour retrouver exactement le calcul
        -- d'avant ce chantier (vx vaut toujours ±2 ici, seul vy varie de 0 à
        -- ±2 : la vitesse va donc de 200, croisière, à 283, rebond en biais).
        local pvx = vel.x / 256
        local pvy = vel.y / 256
        local speed100 = math.sqrt((pvx * pvx + pvy * pvy) * 10000)
        local stretch = math.clamp(100 + (speed100 - 200) / 2, 100, 140)
        self.sprite_scale = vec2(stretch, 200 - stretch)
    end
end

function on_collision_enter(other, my_box, other_box)
    local x = self.position.x

    -- Angle de rebond selon le point d'impact sur la raquette :
    -- centre = tir droit, haut = renvoi vers le haut, bas = renvoi vers le bas.
    local ball_center   = self.position.y + 4
    local paddle_center = other.position.y + 16
    local offset = ball_center - paddle_center
    local vy = math.clamp(offset / 3, -2, 2)   -- en pixels/frame, comme avant v0.19

    sfx.play("PADDLEBOUNCE")

    -- Le choc arrive par le côté : la balle s'écrase en largeur, donc s'allonge
    -- en hauteur. Elle repart du même coup, l'effet dure le temps qu'elle
    -- s'éloigne de la raquette.
    fx   = FX_STRETCH
    fx_t = 0

    -- self.velocity.x est déjà en Q8 : le reprendre tel quel n'a rien à
    -- convertir. Seul `vy`, calculé ci-dessus en pixels, passe à l'échelle Q8
    -- à l'écriture.
    local vx = self.velocity.x
    if x < 120 then
        self.velocity = vec2(math.abs(vx), vy * 256)
    end
    if x >= 120 then
        self.velocity = vec2(-math.abs(vx), vy * 256)
    end
end
