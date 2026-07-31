exports = {
    nouvelle_var = { type = "actor_ref", default = "", label = "nouvelle_var" },
}

function on_start()
    music.play("Dreamy DX")
    -- Le titre est CENTRÉ par sa zone : le script ne compte plus de colonnes.
    text.draw_in("titre", "intro")
end

function on_update()
    -- Machine à écrire dans une zone centrée. La mise en page se fait sur le
    -- texte FINAL et n'est que masquée : le centrage ne bouge pas pendant que
    -- les lettres apparaissent.
    text.draw_in("invite", "intro_02")

    if input.pressed("start") then
        scene.switch("ARENA")
    end
end
