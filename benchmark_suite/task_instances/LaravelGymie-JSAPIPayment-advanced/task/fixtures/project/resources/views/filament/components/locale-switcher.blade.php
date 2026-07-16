<div class="fi-topbar-item">
    <x-filament::dropdown placement="bottom-end" teleport>
        <x-slot name="trigger">
            <x-filament::button
                type="button"
                color="gray"
                outlined
                size="sm"
                title="{{ $this->options[$this->locale]['label'] ?? $this->locale }}"
                aria-label="{{ $this->options[$this->locale]['label'] ?? $this->locale }}"
            >
                <span class="text-base leading-none">{{ $this->currentFlag }}</span>
                <span class="fi-locale-switcher-label text-sm font-medium">
                    {{ $this->options[$this->locale]['label'] ?? $this->locale }}
                </span>
                <span class="sr-only">{{ $this->options[$this->locale]['label'] ?? $this->locale }}</span>
            </x-filament::button>
        </x-slot>

        <x-filament::dropdown.list>
            @foreach ($this->options as $code => $option)
                <x-filament::dropdown.list.item
                    :color="$code === $this->locale ? 'primary' : 'gray'"
                    tag="button"
                    type="button"
                    wire:click="setLocale('{{ $code }}')"
                >
                    <span class="flex items-center gap-2">
                        <span class="text-base leading-none">{{ $option['flag'] }}</span>
                        <span>{{ $option['label'] }}</span>
                    </span>
                </x-filament::dropdown.list.item>
            @endforeach
        </x-filament::dropdown.list>
    </x-filament::dropdown>
</div>
