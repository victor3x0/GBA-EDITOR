function on_start()
    music.play("Dreamy DX")
    display.print(10, 8, "PONG")
    display.print(6, 11, "PRESS START")
end

function on_update()
    if input.pressed("start") then
        scene.switch("PONG")
    end
end
