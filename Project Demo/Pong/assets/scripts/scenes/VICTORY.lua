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
        text.draw_in("victory", "resultat")
    end
    if global.get("winner") == 1 then
        music.play("Sealed DX")
        text.draw_in("victory_02", "resultat")
    end
    -- Ferré à droite — le troisième alignement.
    text.draw_in("victory_03", "invite_fin")
end

function on_update()
    if input.pressed("start") then
        scene.switch("INTRO")
    end
end
