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
    self.velocity = vec2(vx, 1)
    self.rotation = math.atan2(1, vx)
    fx   = FX_POP
    fx_t = 0
end

function on_update()
    local pos = self.position
    local vel = self.velocity
    local n = pos + vel

    -- Rebond vertical sur tiles solides
    if vel.y < 0 then
        if tile.get(n.x, n.y) ~= 0 or tile.get(n.x + 7, n.y) ~= 0 then
            vel.y = -vel.y
            n.y = pos.y
            sfx.play("WALLBOUNCE")
            fx   = FX_SQUASH
            fx_t = 0
        end
    end
    if vel.y > 0 then
        if tile.get(n.x, n.y + 7) ~= 0 or tile.get(n.x + 7, n.y + 7) ~= 0 then
            vel.y = -vel.y
            n.y = pos.y
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

    self.velocity = vel
    self.position = n
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
        -- GBA). vx vaut toujours ±2 ici, seul vy varie (0 à ±2) : la vitesse
        -- va donc de 200 (croisière) à 283 (rebond en biais).
        local speed100 = math.sqrt((vel.x * vel.x + vel.y * vel.y) * 10000)
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
    local vy = math.clamp(offset / 3, -2, 2)

    sfx.play("PADDLEBOUNCE")

    -- Le choc arrive par le côté : la balle s'écrase en largeur, donc s'allonge
    -- en hauteur. Elle repart du même coup, l'effet dure le temps qu'elle
    -- s'éloigne de la raquette.
    fx   = FX_STRETCH
    fx_t = 0

    local vx = self.velocity.x
    if x < 120 then
        self.velocity = vec2(math.abs(vx), vy)
    end
    if x >= 120 then
        self.velocity = vec2(-math.abs(vx), vy)
	end
end

