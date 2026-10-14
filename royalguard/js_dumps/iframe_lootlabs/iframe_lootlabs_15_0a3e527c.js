
    var textsArr = [  "Loot drop incoming - your game link is being summoned.",
        "Your portal to the gaming realm is loading, hang on.",
        "Building the digital bridge to your quest, hold tight.",
        "We're conjuring your magical gaming portal, please be patient.",
        "Crafting the key to your gaming castle, hang on.",
        "Initiating warp speed for your game link creation, hang tight.",
        "Summoning your game link from the ether, hold on.",
        "Hang tight, your XP is about to level up with this new game link.",
        "Spawning your game link, hang tight, don't rage quit.",
        "Cranking the gears for your OP game link, standby.",
        "Health bar is loading, link creation in progress.",
        "Your epic mount to the game world is in the works, be patient.",
        "The blacksmith is busy hammering your game link, BRB.",
        "Reconfiguring your HUD, your link is on its way.",
        "Saddling up your horse to the game, hang on."];
    var loadingText = document.getElementById('loading-text');

    function getRandomText() {
        var randomIndex = Math.floor(Math.random() * textsArr.length);
        return textsArr[randomIndex];
    }

    function updateLoadingText() {
        loadingText.textContent = getRandomText();
    }

    setTimeout(() => {
        var loader = document.querySelector('.rew_loader');
        if (loader) {
            // loader.parentNode.removeChild(loader);
            loader.classList.add('hidden');
        }
    }, 4500);

    // Call the function initially to set a random text when the page loads
    updateLoadingText();
