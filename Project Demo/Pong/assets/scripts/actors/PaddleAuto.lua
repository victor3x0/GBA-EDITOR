-- IA de la raquette : au lieu de copier ball_y à chaque frame (imbattable),
-- elle ne "regarde" la balle que toutes les REACTION_DELAY frames et vise
-- avec une marge d'erreur aléatoire — reflexes moins parfaits, exploitable
-- avec un tir bien placé (angle serré juste après un rafraîchissement).
local target = 76
local reaction_timer = 0
local REACTION_DELAY = 8
local ERROR_MARGIN = 10

function on_update()
    local x = self:get_x()
    local y = self:get_y()

    reaction_timer = reaction_timer + 1
    if reaction_timer >= REACTION_DELAY then
        reaction_timer = 0
        target = global.get("ball_y") - 12 + math.rand(-ERROR_MARGIN, ERROR_MARGIN)
    end

    if y < target then
        y = y + 2
    end
    if y > target then
        y = y - 2
    end

    y = math.clamp(y, 0, 136)
    self:set_pos(x, y)
end
