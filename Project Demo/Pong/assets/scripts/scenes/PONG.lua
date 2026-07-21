exports = {
    nouvelle_var = { type = "int", default = 0, label = "nouvelle_var" },
}

function on_start()
    music.play("Admin Rights - Full DX FAST")
    global.set("score_player", 0)
    global.set("score_auto", 0)
    global.set("ball_y", 76)
    global.set("point_side", -1)
    actor.spawn("Ball", 116, 76)
end

-- Système de jeu : dépouillement des points, condition de victoire et
-- (re)spawn de la balle. Ball.lua ne fait plus que la physique/collision et
-- signale le camp qui encaisse via le global "point_side".
function on_update()
    local side = global.get("point_side")

    if side == 0 then
        sfx.play("GOAL")
        global.set("score_player", global.get("score_player") + 1)
    end
    if side == 1 then
        sfx.play("GoalTaken")
        global.set("score_auto", global.get("score_auto") + 1)
    end

    if side >= 0 then
        global.set("point_side", -1)

        if global.get("score_player") >= 5 then
            sfx.play("GAMEOVER")
            global.set("winner", 0)
            scene.switch("VICTORY")
            return
        end
        if global.get("score_auto") >= 5 then
            sfx.play("GAMEOVER")
            global.set("winner", 1)
            scene.switch("VICTORY")
            return
        end

        -- Fin de round : la balle précédente vient de se détruire elle-même
        -- (Ball.lua), on en instancie une nouvelle pour le round suivant.
        global.set("ball_y", 76)
        actor.spawn("Ball", 116, 76)
    end
end

function on_late_update()
    display.print(9, 2, "%d", global.get("score_player"))
    display.print(20, 2, "%d", global.get("score_auto"))
end
