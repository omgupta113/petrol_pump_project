import connection from '../../db/connection.js';

const PetrolPumpRepository = {
    insertPetrolPump: (params) => {
        return new Promise((resolve, reject) => {
            const query = `
                INSERT INTO \`Petrol Pump\` (\`petrolPumpID\`, \`Name\`, \`Location\`) 
                VALUES (?, ?, ?)
            `;
            connection.query(query, params, (err, results) => {
                if (err) reject(err);
                else resolve(results);
            });
        });
    },

    getAllPetrolPumps: () => {
        return new Promise((resolve, reject) => {
            const query = `
                SELECT \`petrolPumpID\`, \`Name\`, \`Location\`
                FROM \`Petrol Pump\`
            `;
            connection.query(query, (err, results) => {
                if (err) reject(err);
                else resolve(results);
            });
        });
    },

    getPetrolPumpById: (id) => {
        return new Promise((resolve, reject) => {
            const query = `
                SELECT \`petrolPumpID\`, \`Name\`, \`Location\`
                FROM \`Petrol Pump\`
                WHERE \`PetrolPumpID\` = ?
            `;
            connection.query(query, [id], (err, results) => {
                if (err) reject(err);
                else resolve(results[0] || null);
            });
        });
    },

    updatePetrolPump: (params) => {
        return new Promise((resolve, reject) => {
            const query = `
                UPDATE \`Petrol Pump\`
                SET \`Name\` = ?, \`Location\` = ?
                WHERE \`petrolPumpID\` = ?
            `;
            connection.query(query, params, (err, results) => {
                if (err) reject(err);
                else resolve(results);
            });
        });
    },

    deletePetrolPumpById: (id) => {
        return new Promise((resolve, reject) => {
            const query = `
                DELETE FROM \`Petrol Pump\`
                WHERE \`petrolPumpID\` = ?
            `;
            connection.query(query, [id], (err, results) => {
                if (err) reject(err);
                else resolve(results);
            });
        });
    },

    getLastPetrolPumpID: () => {
        return new Promise((resolve, reject) => {
            const query = `
                SELECT \`petrolPumpID\`
                FROM \`Petrol Pump\`
                ORDER BY CAST(SUBSTRING_INDEX(\`petrolPumpID\`, '-', -1) AS UNSIGNED) DESC
                LIMIT 1
            `;
            connection.query(query, (err, results) => {
                if (err) reject(err);
                else resolve(results[0] ? results[0]['petrolPumpID'] : null); // Fixed line
            });
        });
    }
};

export default PetrolPumpRepository;
