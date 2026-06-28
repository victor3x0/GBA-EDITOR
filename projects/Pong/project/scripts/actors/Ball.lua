-- Prefab script : Ball (poolé — max_instances=1)
-- La logique de score et de respawn est dans le script de scène PONG.lua.

function on_start(self)
    self:set_velocity(2, 1)
end

function on_update(self)
    self:apply_velocity()

    -- But à gauche : le joueur droit marque
    if self:get_x() < 8 then
        global.set("goal_scored", 2)
        self:destroy()
    -- But à droite : le joueur gauche marque
    elseif self:get_x() > 232 then
        global.set("goal_scored", 1)
        self:destroy()
    end
end

function on_collision_enter(self, other, my_box, other_box)
    local ball_cy   = self:get_y() + 4
    local paddle_cy = other:get_y() + 16
    local offset    = ball_cy - paddle_cy

    local new_vy
    if offset < -10 then
        new_vy = -3
    elseif offset < -4 then
        new_vy = -2
    elseif offset > 10 then
        new_vy = 3
    elseif offset > 4 then
        new_vy = 2
    else
        new_vy = 0
    end

    local dx = self:get_x() - other:get_x()
    local new_vx
    if dx > 0 then
        new_vx = 3
    else
        new_vx = -3
    end

    self:set_velocity(new_vx, new_vy)
end

function on_tile_collide(self, normal_x, normal_y)
    if normal_y ~= 0 then
        self:set_velocity(self:get_vx(), -self:get_vy())
    elseif normal_x ~= 0 then
        self:set_velocity(-self:get_vx(), self:get_vy())
    end
end
