import { createRouter, createWebHistory } from 'vue-router'
export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./views/HomeView.vue') },
    { path: '/artworks', component: () => import('./views/ArtworksView.vue') },
    { path: '/artworks/:id', component: () => import('./views/ArtworkView.vue') },
    { path: '/account', component: () => import('./views/AccountView.vue') },
    { path: '/admin', component: () => import('./views/AdminView.vue') },
  ],
})
