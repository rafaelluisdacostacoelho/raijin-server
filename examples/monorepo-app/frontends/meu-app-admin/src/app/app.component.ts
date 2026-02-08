import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet],
  template: `
    <div class="min-h-screen bg-gray-100">
      <nav class="bg-indigo-600 text-white p-4">
        <div class="max-w-7xl mx-auto flex justify-between items-center">
          <h1 class="text-xl font-bold">Meu App Admin</h1>
          <span class="text-xs bg-indigo-500 px-2 py-1 rounded">Angular</span>
        </div>
      </nav>
      <main class="max-w-7xl mx-auto p-8">
        <router-outlet />
      </main>
    </div>
  `,
})
export class AppComponent {
  title = 'meu-app-admin';
}
