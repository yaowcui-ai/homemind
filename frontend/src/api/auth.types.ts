export interface User { id: string; username: string; home_id: string }
export interface AuthSession { user: User | null; csrf_token: string; simulation_debug_enabled: boolean }
export interface Credentials { username: string; password: string }
export interface Preferences {
  version: number; comfort_temperature_c: number; sleep_temperature_c: number;
  fan_mode: 'low' | 'auto'; arrival_lead_minutes: number;
}
