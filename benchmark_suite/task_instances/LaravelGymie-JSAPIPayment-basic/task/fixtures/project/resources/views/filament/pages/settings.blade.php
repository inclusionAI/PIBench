<x-filament-panels::page>
    <form wire:submit.prevent="save" class="space-y-6">
        {{ $this->form }}
        <div class="flex justify-end items-center space-x-4">
            <x-filament::button type="submit" wire:loading.class="opacity-50">
                {{ __('app.settings.actions.save_settings') }}
            </x-filament::button>
        </div>
    </form>
</x-filament-panels::page>
