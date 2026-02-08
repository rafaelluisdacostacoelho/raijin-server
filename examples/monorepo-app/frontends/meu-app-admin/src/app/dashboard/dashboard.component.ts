import { Component } from '@angular/core';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  template: `
    <div class="space-y-6">
      <h2 class="text-2xl font-bold text-gray-900">Admin Dashboard</h2>
      <p class="text-gray-600">Painel administrativo Angular — placeholder para expansão.</p>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div class="bg-white rounded-xl border p-6 shadow-sm">
          <h3 class="text-sm font-medium text-gray-500 uppercase">Usuários</h3>
          <p class="text-3xl font-bold mt-2">—</p>
        </div>
        <div class="bg-white rounded-xl border p-6 shadow-sm">
          <h3 class="text-sm font-medium text-gray-500 uppercase">Requisições/min</h3>
          <p class="text-3xl font-bold mt-2">—</p>
        </div>
        <div class="bg-white rounded-xl border p-6 shadow-sm">
          <h3 class="text-sm font-medium text-gray-500 uppercase">Erros (24h)</h3>
          <p class="text-3xl font-bold mt-2">—</p>
        </div>
      </div>
    </div>
  `,
})
export class DashboardComponent {}
