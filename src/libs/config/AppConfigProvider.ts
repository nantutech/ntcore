import { ProviderType, ProviderTypeMapping } from '../../commons/ProviderType';
import yaml = require('js-yaml');
import fs = require('fs');

/**
 * Container setup in AppConfig.
 */
class AppConfigContainer {
    provider: ProviderType;
    namespace?: string;
}
/**
 * Database setup in AppConfig.
 */
class AppConfigDatabase {
    provider: "sqlite" | "postgres";
    path?: string;
    uri?: string;
}
/**
 * Application configuration.
 */
class AppConfig {
    container: AppConfigContainer;
    database: AppConfigDatabase;
}

function getContainerProviderConfig(config: any): AppConfigContainer {
    const provider = ProviderTypeMapping[config['container'].provider.type];
    switch(provider) {
        case ProviderType.KUBERNETES: return { provider: provider, namespace: config['container'].provider.namespace };
        case ProviderType.DOCKER: return { provider: provider };
        default: throw new Error("Invalid container provider");
    }
}

function getDatabtaseProviderConfig(config: any): AppConfigDatabase {
    const provider = config['database'].provider.type;
    switch(provider) {
        case "sqlite": return { provider: provider, path: config['database'].provider.path };
        case "postgres": return { provider: provider, uri: config['database'].provider.uri };
        default: throw new Error("Invalid databse provider");
    }
}

function getAppConfig(): AppConfig {
    console.log(`Parsing application configuration ... `);
    const config = yaml.load(fs.readFileSync('app-config/ntcore.yml', 'utf8'));
    return { 
        container: getContainerProviderConfig(config),
        database: getDatabtaseProviderConfig(config)
    };
}

export const appConfig = getAppConfig();