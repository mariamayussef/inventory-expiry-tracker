import EmbeddedPostgres from 'embedded-postgres';
import {existsSync, mkdirSync} from 'node:fs';
mkdirSync('.local',{recursive:true});
const pg=new EmbeddedPostgres({databaseDir:'.local/postgres',user:'inventory',password:process.env.LOCAL_DB_PASSWORD || 'inventory',port:55432,persistent:true,authMethod:'scram-sha-256',postgresFlags:['-h','127.0.0.1'],onLog:()=>{},onError:console.error});
if(!existsSync('.local/postgres/PG_VERSION')) await pg.initialise();
await pg.start();
const client=pg.getPgClient(); await client.connect();
for (const name of ['inventory','inventory_test']) {
  if(!(await client.query('SELECT 1 FROM pg_database WHERE datname=$1',[name])).rowCount) await client.query(`CREATE DATABASE ${name}`);
}
await client.end();
console.log('Local PostgreSQL listening at 127.0.0.1:55432. Data persists in .local/postgres. Ctrl+C to stop.');
let stopping=false;
for(const signal of ['SIGTERM','SIGINT']) process.on(signal,async()=>{if(stopping)return;stopping=true;await pg.stop();process.exit(0)});
await new Promise(()=>{});
