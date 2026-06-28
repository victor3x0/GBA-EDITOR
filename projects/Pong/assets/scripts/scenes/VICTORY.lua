function on_start()
    if global.get("winner") == 0 then
        display.print(4, 8, "PLAYER WINS!")
    end
    if global.get("winner") == 1 then
        display.print(5, 8, "CPU WINS!")
    end
    display.print(6, 11, "PRESS START")
end

function on_update()
    if input.pressed("start") then
        scene.switch("INTRO")
    end
end
