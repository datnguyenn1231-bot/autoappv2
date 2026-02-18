import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
    const appName = ref('AuraSplit')
    const version = ref('2.0.0-alpha')
    const currentFeature = ref('ai-cut')
    const isLoading = ref(false)
    const statusMessage = ref('Ready')

    function setLoading(loading: boolean, message?: string) {
        isLoading.value = loading
        if (message) statusMessage.value = message
    }

    function setStatus(message: string) {
        statusMessage.value = message
    }

    return {
        appName,
        version,
        currentFeature,
        isLoading,
        statusMessage,
        setLoading,
        setStatus
    }
})
