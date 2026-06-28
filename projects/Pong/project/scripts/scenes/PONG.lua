-- Scene script : PONG
-- Toute la logique de jeu est ici. Les actors (Ball, Paddles) ne font que
-- leur comportement propre et signalent via les globals.

local respawn_timer = 0
local RESPAWN_DELAY = 120   -- 2 secondes à 60 fps
local WIN_SCORE     = 10

function on_start()
    global.set("score_left",  0)
    global.set("score_right", 0)
    global.set("goal_scored", 0)
    actor.spawn("Ball", 120, 76)
end

function on_update()
    -- Affichage scores (toujours mis à jour)
    display.print(12, 2, "%d", global.get("score_left"))
    display.print(17, 2, "%d", global.get("score_right"))

    -- Détection d'un but (signal posé par Ball.lua avant self:destroy())
    local goal = global.get("goal_scored")
    if goal ~= 0 then
        if goal == 1 then
            global.set("score_left",  global.get("score_left")  + 1)
        else
            global.set("score_right", global.get("score_right") + 1)
        end
        global.set("goal_scored", 0)
        respawn_timer = RESPAWN_DELAY
    end

    -- Compte à rebours avant respawn
    if respawn_timer > 0 then
        respawn_timer = respawn_timer - 1

        if respawn_timer == 0 then
            local sl = global.get("score_left")
            local sr = global.get("score_right")

            if sl >= WIN_SCORE then
                scene.switch("VICTORY")
            elseif sr >= WIN_SCORE then
                scene.switch("VICTORY")
            else
                actor.spawn("Ball", 120, 76)
            end
        end
    end
end
