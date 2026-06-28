function on_start()
    local vx = 2
    if math.rand(0, 1) == 0 then
        vx = -2
    end
    self:set_velocity(vx, 1)
end

function on_update()
    local x = self:get_x()
    local y = self:get_y()
    local vx = self:get_vx()
    local vy = self:get_vy()

    local nx = x + vx
    local ny = y + vy

    -- Rebond vertical sur tiles solides
    if vy < 0 then
        if tile.get(nx, ny) ~= 0 or tile.get(nx + 7, ny) ~= 0 then
            vy = -vy
            ny = y
        end
    end
    if vy > 0 then
        if tile.get(nx, ny + 7) ~= 0 or tile.get(nx + 7, ny + 7) ~= 0 then
            vy = -vy
            ny = y
        end
    end

    -- Sortie par la gauche : point pour l'auto
    if nx < 0 then
        global.set("score_auto", global.get("score_auto") + 1)
        self:set_pos(116, 76)
        self:set_velocity(2, 1)
        return
    end

    -- Sortie par la droite : point pour le joueur
    if nx > 240 then
        global.set("score_player", global.get("score_player") + 1)
        self:set_pos(116, 76)
        self:set_velocity(-2, 1)
        return
    end

    self:set_velocity(vx, vy)
    self:set_pos(nx, ny)
    global.set("ball_y", ny)
end

function on_collision_enter(other, my_box, other_box)
    local x = self:get_x()
    local vy = self:get_vy()
    if x < 120 then
        self:set_velocity(math.abs(self:get_vx()), vy)
    end
    if x >= 120 then
        self:set_velocity(-math.abs(self:get_vx()), vy)
    end
end
