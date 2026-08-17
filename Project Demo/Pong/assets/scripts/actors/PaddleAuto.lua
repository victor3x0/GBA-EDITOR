-- IA de la raquette : au lieu de copier ball_y à chaque frame (imbattable),
-- elle ne "regarde" la balle que toutes les REACTION_DELAY frames et vise
-- avec une marge d'erreur aléatoire — reflexes moins parfaits, exploitable
-- avec un tir bien placé (angle serré juste après un rafraîchissement).
local target = 76
local reaction_timer = 0
local REACTION_DELAY = 8
local ERROR_MARGIN = 10

-- Même réaction au choc que la raquette du joueur (cf. PaddlePlayer.lua) :
-- écrasement en largeur et léger dévers, sur un compteur partagé parce que les
-- deux helpers écrivent des canaux différents du sprite.
local hit_t = 99   -- au-delà des deux durées : aucun effet au démarrage

function on_update()
    local pos = self.position

    reaction_timer = reaction_timer + 1
    if reaction_timer >= REACTION_DELAY then
        reaction_timer = 0
        target = global.get("ball_y") - 12 + math.rand(-ERROR_MARGIN, ERROR_MARGIN)
    end

    if pos.y < target then
        pos.y = pos.y + 2
    end
    if pos.y > target then
        pos.y = pos.y - 2
    end

    pos.y = math.clamp(pos.y, 0, 136)
    self.position = pos

    hit_t = hit_t + 1
    self:stretch(hit_t, 12, 30)
    self:wobble(hit_t, 18, 6)
end

function on_collision_enter(other, my_box, other_box)
    hit_t = 0
end
