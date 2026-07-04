function on_update()
    local x = self:get_x()
    local y = self:get_y()

    if input.held("up") then
        y = y - 2
    end
    if input.held("down") then
        y = y + 2
    end

    y = math.clamp(y, 0, 136)
    self:set_pos(x, y)
end
