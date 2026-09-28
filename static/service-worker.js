const CACHE_NAME = "sistema-manutencao-v2";

const FILES_TO_CACHE = [
    "/",
    "/login"
];


// =========================================================
// INSTALAÇÃO
// =========================================================

self.addEventListener("install", event => {

    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(FILES_TO_CACHE))
    );

    self.skipWaiting();
});


// =========================================================
// ATIVAÇÃO
// =========================================================

self.addEventListener("activate", event => {

    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys
                    .filter(key => key !== CACHE_NAME)
                    .map(key => caches.delete(key))
            )
        )
    );

    self.clients.claim();
});


// =========================================================
// FUNCIONAMENTO OFFLINE
// =========================================================

self.addEventListener("fetch", event => {

    event.respondWith(
        fetch(event.request)
            .catch(() => caches.match(event.request))
    );

});


// =========================================================
// RECEBER NOTIFICAÇÃO PUSH
// =========================================================

self.addEventListener("push", event => {

    let data = {};

    try {

        if (event.data) {
            data = event.data.json();
        }

    } catch (error) {

        console.error(
            "Erro ao interpretar notificação push:",
            error
        );

    }

    const title =
        data.title ||
        "Sistema de Manutenção";

    const options = {

        body:
            data.body ||
            "Nova solicitação de manutenção.",

        icon:
            "/static/icon-192.png",

        badge:
            "/static/icon-192.png",

        data: {
            url:
                data.url ||
                "/"
        },

        vibrate: [
            200,
            100,
            200
        ],

        tag: "sistema-manutencao",

        renotify: true

    };

    event.waitUntil(

        self.registration.showNotification(
            title,
            options
        )

    );

});


// =========================================================
// CLIQUE NA NOTIFICAÇÃO
// =========================================================

self.addEventListener(
    "notificationclick",
    event => {

        event.notification.close();

        const url =
            event.notification.data?.url ||
            "/";

        event.waitUntil(

            clients
                .matchAll({
                    type: "window",
                    includeUncontrolled: true
                })
                .then(clientList => {

                    for (const client of clientList) {

                        if (
                            "focus" in client
                        ) {

                            client.navigate(
                                url
                            );

                            return client.focus();

                        }

                    }

                    if (
                        clients.openWindow
                    ) {

                        return clients.openWindow(
                            url
                        );

                    }

                })

        );

    }
);
