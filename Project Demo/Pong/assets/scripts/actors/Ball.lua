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
            sfx.play("WALLBOUNCE")
        end
    end
    if vy > 0 then
        if tile.get(nx, ny + 7) ~= 0 or tile.get(nx + 7, ny + 7) ~= 0 then
            vy = -vy
            ny = y
            sfx.play("WALLBOUNCE")
        end
    end

    -- Sortie de terrain : la balle ne fait que signaler le camp qui encaisse
    -- (point_side) puis se détruit — la scène PONG gère score/victoire/spawn.
    if nx < 0 then
        global.set("point_side", 1)
        self:destroy()
        return
    end
    if nx > 240 then
        global.set("point_side", 0)
        self:destroy()
        return
    end

    self:set_velocity(vx, vy)
    self:set_pos(nx, ny)
    global.set("ball_y", ny)
end

function on_collision_enter(other, my_box, other_box)
    local x = self:get_x()

    -- Angle de rebond selon le point d'impact sur la raquette :
    -- centre = tir droit, haut = renvoi vers le haut, bas = renvoi vers le bas.
    local ball_center   = self:get_y() + 4
    local paddle_center = other:get_y() + 16
    local offset = ball_center - paddle_center
    local vy = math.clamp(offset / 3, -2, 2)

    sfx.play("PADDLEBOUNCE")

    if x < 120 then
        self:set_velocity(math.abs(self:get_vx()), vy)
    end
    if x >= 120 then
        self:set_velocity(-math.abs(self:get_vx()), vy)
    end
end

function on_button_r()

end
