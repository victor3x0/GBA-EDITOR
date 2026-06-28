-- Actor script : PaddleAuto
-- Actor       : PADDLE_AUTO
-- IA simple : suit la balle verticalement

exports = {
    speed = { type = "int", default = 1, label = "Speed", min = 1, max = 6 },
}

function on_start(self)
    self:play_anim("Idle")
end

function on_update(self)
    local ball = get_actor("BALL")
    local dy = ball:get_y() - self:get_y()
    if dy > 4 then
        self:move(0, speed)
    elseif dy < -4 then
        self:move(0, -speed)
    end
    -- Bornes écran
    if self:get_y() < 0 then self:set_pos(self:get_x(), 0) end
    if self:get_y() > 136 then self:set_pos(self:get_x(), 136) end
end
