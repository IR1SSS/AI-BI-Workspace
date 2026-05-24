<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <strong>AI BI Workspace</strong>
        <span>Local analytics stack</span>
      </div>
      <router-link to="/datasets">Datasets</router-link>
      <router-link to="/dashboards">Dashboards</router-link>
    </aside>
    <main class="main">
      <router-view />
    </main>
  </div>
</template>
