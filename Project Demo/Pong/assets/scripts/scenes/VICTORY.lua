exports = {
    Test = { type = "int", default = 3, label = "Test" },
    nouvelle_var = { type = "string", default = "", label = "nouvelle_var" },
}

function on_start()
    -- Deux libellés de LONGUEURS DIFFÉRENTES dans la MÊME zone : c'est la zone
    -- qui les centre, là où le script devait auparavant coder une colonne par
    -- cas (4 pour « PLAYER WINS! », 5 pour « CPU WINS! »).
    if global.get("winner") == 0 then
        music.play("Claimed DX")
        text.draw_in("resultat", "victory")
    end
    if global.get("winner") == 1 then
        music.play("Sealed DX")
        text.draw_in("resultat", "victory_02")
    end
    -- Ferré à droite — le troisième alignement.
    text.draw_in("invite_fin", "victory_03")
end

function on_update()
    if input.pressed("start") then
        scene.switch("INTRO")
    end
end
