function on_start()
    display.print(8, 5, "PONG")
    display.print(5, 9, "Appuyez sur START")
end

function on_update()
    if input.pressed("start") then
        scene.switch("PONG")
    end
end

function on_late_update()
end
