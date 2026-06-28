function on_update()
    local x = self:get_x()
    local y = self:get_y()
    local target = global.get("ball_y") - 12

    if y < target then
        y = y + 2
    end
    if y > target then
        y = y - 2
    end

    y = math.clamp(y, 0, 136)
    self:set_pos(x, y)
end
