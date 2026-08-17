exports = {
    nouvelle_var = { type = "int", default = 6, label = "nouvelle_var", min = 0, max = 10 },
}

-- Réaction au choc : la balle arrive par le côté, la raquette s'écrase donc en
-- largeur (stretch) et part un peu de travers (wobble). Les deux helpers
-- écrivent des canaux différents du sprite — l'échelle et la rotation — ils
-- peuvent partager le même compteur, et chacun retombe seul au neutre passé sa
-- durée. D'où l'appel à chaque frame, sans condition : il n'y a rien à éteindre.
local hit_t = 99   -- au-delà des deux durées : aucun effet au démarrage

function on_update()
    local pos = self.position

    if input.held("up") then
        pos.y = pos.y - 2
    end
    if input.held("down") then
        pos.y = pos.y + 2
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
