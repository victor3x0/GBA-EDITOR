function on_start()
    global.set("score_player", 0)
    global.set("score_auto", 0)
    global.set("ball_y", 76)
    actor.spawn("Ball", 116, 76)
end

function on_update()
    if global.get("score_player") >= 5 then
        global.set("winner", 0)
        scene.switch("VICTORY")
    end
    if global.get("score_auto") >= 5 then
        global.set("winner", 1)
        scene.switch("VICTORY")
    end
end

function on_late_update()
    display.print(9, 0, "%d", global.get("score_player"))
    display.print(20, 0, "%d", global.get("score_auto"))
end
