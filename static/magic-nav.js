(function () {
    // Prevent multiple injections
    if (window.MagicNavLoaded) return;
    window.MagicNavLoaded = true;

    async function initMagicNav() {
        try {
            // Add Google Font for Outfit
            const fontLink = document.createElement('link');
            fontLink.rel = 'stylesheet';
            fontLink.href = 'https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600&display=swap';
            document.head.appendChild(fontLink);

            // Fetch services from the proxy host
            const response = await fetch('/portal/services.json');
            if (!response.ok) return;
            const data = await response.json();
            const services = data.services || [];

            // Create Trigger Zone
            const trigger = document.createElement('div');
            trigger.className = 'magic-nav-trigger';
            document.body.appendChild(trigger);

            // Create Container
            const container = document.createElement('div');
            container.id = 'magic-nav-container';

            // Add Logo/Back button
            const logo = document.createElement('div');
            logo.className = 'magic-nav-logo';
            logo.innerHTML = '<span style="color:var(--cyan);font-weight:800">M</span>';
            logo.title = 'Zurück zum Magic Hub';
            logo.onclick = () => window.location.href = '/portal.html';
            container.appendChild(logo);

            container.appendChild(document.createElement('div')).className = 'magic-nav-divider';

            // Add Services
            const currentPath = window.location.pathname;
            services.forEach(service => {
                const item = document.createElement('a');
                item.className = 'magic-nav-item';
                item.href = service.url || '#';
                item.setAttribute('data-tooltip', service.name);

                // Favicon logic
                if (service.icon_url) {
                    const img = document.createElement('img');
                    img.src = service.icon_url;
                    img.onerror = () => {
                        item.innerHTML = `<i class="fas ${service.icon || 'fa-globe'}"></i>`;
                    };
                    item.appendChild(img);
                } else {
                    item.innerHTML = `<i class="fas ${service.icon || 'fa-globe'}"></i>`;
                }

                // Check if active
                if (service.url && currentPath.includes(service.url.split(':8443')[1] || '---')) {
                    item.classList.add('active');
                }

                container.appendChild(item);
            });

            document.body.appendChild(container);

            // Show animation
            setTimeout(() => {
                container.classList.add('visible');
                setTimeout(() => {
                    if (!container.matches(':hover')) {
                        container.classList.remove('visible');
                    }
                }, 3000);
            }, 500);

        } catch (e) {
            console.warn('Magic Nav suppressed:', e);
        }
    }

    if (document.readyState === 'complete') {
        initMagicNav();
    } else {
        window.addEventListener('load', initMagicNav);
    }
})();
