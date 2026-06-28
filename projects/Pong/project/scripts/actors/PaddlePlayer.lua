-- Actor script : PaddlePlayer
-- Actor       : PADDLE_PLAYER

exports = {
    speed = { type = "int", default = 2, label = "Speed", min = 1, max = 8 },
}

function on_start(self)
    self:play_anim("Idle")
end

function on_update(self)
    if input.held("up") then
        self:move(0, -speed)
    end
    if input.held("down") then
        self:move(0, speed)
    end
    -- Bornes écran
    if self:get_y() < 0 then self:set_pos(self:get_x(), 0) end
    if self:get_y() > 136 then self:set_pos(self:get_x(), 136) end
end
